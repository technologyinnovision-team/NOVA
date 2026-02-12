import xml.etree.ElementTree as ET
from datetime import datetime
from flask import current_app
from models import db
from models.blog import BlogPost, BlogCategory, BlogTag
from models.user import User
from utils.validators import generate_slug
from utils.upload import download_file_from_url
import html as html_module
import re

def clean_html_content(content):
    """Clean WordPress-specific HTML tags and comments"""
    if not content:
        return ''
    
    # Remove WordPress block comments
    content = re.sub(r'<!--\s*\/?wp:[\s\S]*?-->', '', content)
    
    # Remove other HTML comments
    content = re.sub(r'<!--[\s\S]*?-->', '', content)
    
    return content.strip()

def extract_text_from_html(html_content, max_length=200):
    """Extract plain text from HTML for excerpt generation"""
    if not html_content:
        return ''
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', html_content)
    # Decode HTML entities
    text = html_module.unescape(text)
    # Clean whitespace
    text = ' '.join(text.split())
    
    # Truncate
    if len(text) > max_length:
        text = text[:max_length] + '...'
    
    return text

def parse_wp_date(date_str):
    """Parse WordPress date string to datetime object"""
    try:
        # WordPress dates are usually in format: YYYY-MM-DD HH:MM:SS
        return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
    except:
        try:
            # Try alternative format
            return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S %z')
        except:
            return None

def get_or_create_user(author_login, author_email, author_name):
    """Get existing user or create new one for author"""
    # Try to find existing user by username or email
    user = User.query.filter(
        (User.username == author_login) | (User.email == author_email)
    ).first()
    
    if not user:
        # Create new user with minimal permissions (Editor role)
        from models.user import Role
        editor_role = Role.query.filter_by(name='Editor').first()
        if not editor_role:
            editor_role = Role.query.first()  # Fallback to first role
        
        user = User(
            username=author_login or author_name or 'imported_user',
            email=author_email or f"{author_login}@imported.local",
            role_id=editor_role.id if editor_role else None,
            is_active=True
        )
        # Set a random password hash (user can reset later)
        from utils.auth import hash_password
        user.password_hash = hash_password('changeme123')
        db.session.add(user)
        db.session.flush()
    
    return user

def get_or_create_category(name, slug=None, description=None):
    """Get or create blog category"""
    if not slug:
        slug = generate_slug(name)
    
    category = BlogCategory.query.filter_by(slug=slug).first()
    if not category:
        category = BlogCategory(
            name=name,
            slug=slug,
            description=description
        )
        db.session.add(category)
        db.session.flush()
    
    return category

def get_or_create_tag(name):
    """Get or create blog tag"""
    slug = generate_slug(name)
    tag = BlogTag.query.filter_by(slug=slug).first()
    if not tag:
        tag = BlogTag(name=name, slug=slug)
        db.session.add(tag)
        db.session.flush()
    
    return tag

def find_featured_image_url(item_element, attachments_map):
    """Find featured image URL from post meta or attachments"""
    # Look for _thumbnail_id in postmeta
    for postmeta in item_element.findall('.//{http://wordpress.org/export/1.2/}postmeta'):
        meta_key = postmeta.find('{http://wordpress.org/export/1.2/}meta_key')
        meta_value = postmeta.find('{http://wordpress.org/export/1.2/}meta_value')
        
        if meta_key is not None and meta_key.text == '_thumbnail_id':
            thumbnail_id = meta_value.text if meta_value is not None else None
            if thumbnail_id and thumbnail_id in attachments_map:
                return attachments_map[thumbnail_id]
    
    return None

def import_wordpress_xml(file, skip_existing=True, update_existing=False):
    """Import WordPress XML export file"""
    result = {
        'created': 0,
        'updated': 0,
        'skipped': 0,
        'errors': 0,
        'error_list': []
    }
    
    try:
        # Parse XML file
        tree = ET.parse(file)
        root = tree.getroot()
        
        # Define namespaces
        namespaces = {
            'content': 'http://purl.org/rss/1.0/modules/content/',
            'excerpt': 'http://wordpress.org/export/1.2/excerpt/',
            'wp': 'http://wordpress.org/export/1.2/',
            'dc': 'http://purl.org/dc/elements/1.1/'
        }
        
        # First pass: Collect authors and attachments
        authors_map = {}
        attachments_map = {}
        
        channel = root.find('channel')
        if channel is None:
            raise ValueError('Invalid WordPress XML format: no channel element found')
        
        # Extract authors
        for author in channel.findall('.//{http://wordpress.org/export/1.2/}author'):
            author_login = author.find('{http://wordpress.org/export/1.2/}author_login')
            author_email = author.find('{http://wordpress.org/export/1.2/}author_email')
            author_name = author.find('{http://wordpress.org/export/1.2/}author_display_name')
            
            if author_login is not None:
                user = get_or_create_user(
                    author_login.text if author_login.text else 'unknown',
                    author_email.text if author_email is not None and author_email.text else None,
                    author_name.text if author_name is not None and author_name.text else None
                )
                authors_map[author_login.text] = user
        
        # Extract attachments (for featured images)
        for item in channel.findall('item'):
            post_type = item.find('{http://wordpress.org/export/1.2/}post_type')
            if post_type is not None and post_type.text == 'attachment':
                post_id = item.find('{http://wordpress.org/export/1.2/}post_id')
                attachment_url = item.find('{http://wordpress.org/export/1.2/}attachment_url')
                
                if post_id is not None and attachment_url is not None:
                    attachments_map[post_id.text] = attachment_url.text
        
        # Second pass: Import posts
        items = channel.findall('item')
        
        for item in items:
            try:
                post_type = item.find('{http://wordpress.org/export/1.2/}post_type')
                if post_type is None or post_type.text != 'post':
                    continue
                
                # Get post status
                status_elem = item.find('{http://wordpress.org/export/1.2/}status')
                wp_status = status_elem.text if status_elem is not None else 'draft'
                
                # Skip trash/pending/future posts
                if wp_status in ['trash', 'pending', 'future']:
                    result['skipped'] += 1
                    continue
                
                # Map WordPress status to our status
                status_map = {
                    'publish': 'published',
                    'draft': 'draft',
                    'private': 'private',
                    'inherit': 'draft'
                }
                status = status_map.get(wp_status, 'draft')
                
                # Extract title
                title_elem = item.find('title')
                title = title_elem.text if title_elem is not None and title_elem.text else 'Untitled'
                
                # Extract slug
                post_name = item.find('{http://wordpress.org/export/1.2/}post_name')
                slug = post_name.text if post_name is not None and post_name.text else generate_slug(title)
                # Clean slug (remove __trashed suffix if present)
                slug = slug.replace('__trashed', '')
                
                # Check if post already exists
                existing_post = BlogPost.query.filter_by(slug=slug).first()
                if existing_post:
                    if skip_existing and not update_existing:
                        result['skipped'] += 1
                        continue
                    elif not update_existing:
                        result['skipped'] += 1
                        continue
                
                # Extract content
                content_elem = item.find('{http://purl.org/rss/1.0/modules/content/}encoded')
                content = content_elem.text if content_elem is not None and content_elem.text else ''
                content = clean_html_content(content)
                
                # Extract excerpt
                excerpt_elem = item.find('{http://wordpress.org/export/1.2/excerpt/}encoded')
                excerpt = excerpt_elem.text if excerpt_elem is not None and excerpt_elem.text else ''
                excerpt = clean_html_content(excerpt)
                if not excerpt and content:
                    excerpt = extract_text_from_html(content, 200)
                
                # Extract dates
                post_date = item.find('{http://wordpress.org/export/1.2/}post_date')
                published_at = None
                if post_date is not None and post_date.text:
                    published_at = parse_wp_date(post_date.text)
                    if status == 'published' and not published_at:
                        published_at = datetime.utcnow()
                
                # Get author
                creator = item.find('{http://purl.org/dc/elements/1.1/}creator')
                author_username = creator.text if creator is not None and creator.text else None
                author = authors_map.get(author_username) if author_username else None
                if not author:
                    # Use first available user or create default
                    author = User.query.first()
                    if not author:
                        author = get_or_create_user('admin', 'admin@imported.local', 'Admin')
                
                # Find featured image
                featured_image_url = find_featured_image_url(item, attachments_map)
                featured_image = None
                if featured_image_url:
                    try:
                        featured_image = download_file_from_url(featured_image_url, folder='blog')
                    except Exception as e:
                        current_app.logger.warning(f"Failed to download featured image {featured_image_url}: {e}")
                        featured_image = featured_image_url  # Fallback to original URL
                
                # Create or update post
                if existing_post and update_existing:
                    existing_post.title = title
                    existing_post.content = content
                    existing_post.excerpt = excerpt
                    existing_post.status = status
                    existing_post.published_at = published_at
                    existing_post.featured_image = featured_image
                    post = existing_post
                    result['updated'] += 1
                else:
                    post = BlogPost(
                        title=title,
                        slug=slug,
                        content=content,
                        excerpt=excerpt,
                        featured_image=featured_image,
                        status=status,
                        published_at=published_at,
                        author_id=author.id
                    )
                    db.session.add(post)
                    db.session.flush()
                    result['created'] += 1
                
                # Handle categories
                post.categories.clear()
                for category in item.findall('category'):
                    domain = category.get('domain')
                    if domain == 'category':
                        category_name = category.text if category.text else None
                        if category_name:
                            cat_slug = generate_slug(category_name)
                            blog_category = get_or_create_category(category_name, cat_slug)
                            if blog_category not in post.categories:
                                post.categories.append(blog_category)
                
                # Handle tags
                post.tags.clear()
                for category in item.findall('category'):
                    domain = category.get('domain')
                    if domain == 'post_tag':
                        tag_name = category.text if category.text else None
                        if tag_name:
                            blog_tag = get_or_create_tag(tag_name)
                            if blog_tag not in post.tags:
                                post.tags.append(blog_tag)
                
                db.session.commit()
                
            except Exception as e:
                db.session.rollback()
                result['errors'] += 1
                error_msg = f"Error importing post '{title if 'title' in locals() else 'Unknown'}': {str(e)}"
                result['error_list'].append(error_msg)
                current_app.logger.error(error_msg)
                continue
        
        return result
        
    except Exception as e:
        db.session.rollback()
        result['errors'] += 1
        result['error_list'].append(f"Fatal error: {str(e)}")
        current_app.logger.error(f"WordPress import failed: {e}")
        return result

