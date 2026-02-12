from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import db
from models.blog import BlogPost, BlogCategory, BlogTag
from models.user import User
from utils.permissions import login_required
from utils.upload import upload_file_local, delete_file_local, allowed_file, download_file_from_url
from utils.validators import generate_slug
from werkzeug.utils import secure_filename
from datetime import datetime
from sqlalchemy import or_
import html
import re

blogs = Blueprint('blogs', __name__, url_prefix='/admin/blogs')

@blogs.route('/')
@login_required
def list():
    """Blog listing page with filtering and search"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '')
    category_filter = request.args.get('category', '')
    
    query = BlogPost.query
    
    # Search filter
    if search:
        query = query.filter(
            or_(
                BlogPost.title.ilike(f'%{search}%'),
                BlogPost.content.ilike(f'%{search}%'),
                BlogPost.excerpt.ilike(f'%{search}%')
            )
        )
    
    # Status filter
    if status_filter:
        query = query.filter(BlogPost.status == status_filter)
    
    # Category filter
    if category_filter:
        try:
            category_id = int(category_filter)
            query = query.join(BlogPost.categories).filter(BlogCategory.id == category_id)
        except:
            pass
    
    # Order by latest first
    query = query.order_by(BlogPost.created_at.desc())
    
    # Pagination
    per_page = 20
    posts_paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Counts by status
    total_count = BlogPost.query.count()
    published_count = BlogPost.query.filter_by(status='published').count()
    draft_count = BlogPost.query.filter_by(status='draft').count()
    private_count = BlogPost.query.filter_by(status='private').count()
    
    # Get all categories for filter dropdown
    all_categories = BlogCategory.query.order_by(BlogCategory.name).all()
    
    return render_template('blogs/list.html',
                         posts=posts_paginated.items,
                         pagination=posts_paginated,
                         search=search,
                         status_filter=status_filter,
                         category_filter=category_filter,
                         categories=all_categories,
                         total_count=total_count,
                         published_count=published_count,
                         draft_count=draft_count,
                         private_count=private_count)


@blogs.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create blog post page"""
    if request.method == 'POST':
        try:
            # Basic fields
            title = request.form.get('title', '').strip()
            if not title:
                flash('Blog post title is required.', 'error')
                return render_template('blogs/form.html',
                                     post=None,
                                     categories=get_all_categories(),
                                     tags=get_all_tags(),
                                     form_data=request.form)
            
            slug = request.form.get('slug', '').strip() or generate_slug(title)
            
            # Check if slug exists
            if BlogPost.query.filter_by(slug=slug).first():
                slug = f"{slug}-{int(datetime.now().timestamp())}"
            
            content = request.form.get('content', '').strip()
            if not content:
                flash('Blog post content is required.', 'error')
                return render_template('blogs/form.html',
                                     post=None,
                                     categories=get_all_categories(),
                                     tags=get_all_tags(),
                                     form_data=request.form)
            
            excerpt = request.form.get('excerpt', '').strip() or None
            
            # Handle featured image
            featured_image = None
            if 'featured_image' in request.files:
                file = request.files['featured_image']
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    timestamp = int(datetime.now().timestamp())
                    try:
                        featured_image = upload_file_local(file, folder='blogs')
                    except Exception as e:
                        flash(f'Error uploading featured image: {str(e)}', 'error')
            
            # If no file upload but URL provided
            if not featured_image and request.form.get('featured_image_url'):
                featured_image = request.form.get('featured_image_url', '').strip() or None
            
            # Parse published_at date
            published_at = None
            if request.form.get('published_at'):
                try:
                    published_at = datetime.strptime(request.form.get('published_at'), '%Y-%m-%dT%H:%M')
                except:
                    pass
            
            status = request.form.get('status', 'draft')
            if status == 'published' and not published_at:
                published_at = datetime.utcnow()
            
            # Get current user as author
            from utils.auth import get_current_user
            current_user = get_current_user()
            
            post = BlogPost(
                title=title,
                slug=slug,
                content=content,
                excerpt=excerpt,
                featured_image=featured_image,
                status=status,
                published_at=published_at,
                author_id=current_user.id if current_user else 1,
                meta_title=request.form.get('meta_title', '').strip() or None,
                meta_description=request.form.get('meta_description', '').strip() or None,
                meta_keywords=request.form.get('meta_keywords', '').strip() or None,
            )
            
            db.session.add(post)
            db.session.flush()
            
            # Handle categories
            category_ids = request.form.getlist('categories')
            for category_id in category_ids:
                try:
                    category = BlogCategory.query.get(int(category_id))
                    if category:
                        post.categories.append(category)
                except:
                    pass
            
            # Handle tags - split comma-separated string
            tags_input = request.form.get('tags', '').strip()
            if tags_input:
                tag_names = [t.strip() for t in tags_input.split(',') if t.strip()]
                for tag_name in tag_names:
                    tag_slug = generate_slug(tag_name)
                    tag = BlogTag.query.filter_by(slug=tag_slug).first()
                    if not tag:
                        tag = BlogTag(name=tag_name, slug=tag_slug)
                        db.session.add(tag)
                        db.session.flush()
                    if tag not in post.tags:
                        post.tags.append(tag)
            
            db.session.commit()
            flash('Blog post created successfully!', 'success')
            return redirect(url_for('blogs.list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating blog post: {str(e)}', 'error')
            return render_template('blogs/form.html',
                                 post=None,
                                 categories=get_all_categories(),
                                 tags=get_all_tags(),
                                 form_data=request.form)
    
    return render_template('blogs/form.html',
                         post=None,
                         categories=get_all_categories(),
                         tags=get_all_tags())


@blogs.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Edit blog post page"""
    post = BlogPost.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            if not title:
                flash('Blog post title is required.', 'error')
                return render_template('blogs/form.html',
                                     post=post,
                                     categories=get_all_categories(),
                                     tags=get_all_tags())
            
            slug = request.form.get('slug', '').strip() or generate_slug(title)
            
            # Check if slug exists (excluding current post)
            existing = BlogPost.query.filter_by(slug=slug).first()
            if existing and existing.id != post.id:
                slug = f"{slug}-{int(datetime.now().timestamp())}"
            
            content = request.form.get('content', '').strip()
            if not content:
                flash('Blog post content is required.', 'error')
                return render_template('blogs/form.html',
                                     post=post,
                                     categories=get_all_categories(),
                                     tags=get_all_tags())
            
            excerpt = request.form.get('excerpt', '').strip() or None
            
            # Handle featured image
            if 'featured_image' in request.files:
                file = request.files['featured_image']
                if file and file.filename and allowed_file(file.filename):
                    # Delete old image if exists
                    if post.featured_image:
                        try:
                            delete_file_local(post.featured_image)
                        except:
                            pass
                    
                    try:
                        post.featured_image = upload_file_local(file, folder='blogs')
                    except Exception as e:
                        flash(f'Error uploading featured image: {str(e)}', 'error')
            
            # If URL provided and no file upload
            if request.form.get('featured_image_url') and 'featured_image' not in request.files:
                if post.featured_image and post.featured_image != request.form.get('featured_image_url'):
                    try:
                        delete_file_local(post.featured_image)
                    except:
                        pass
                post.featured_image = request.form.get('featured_image_url', '').strip() or None
            
            # Parse published_at date
            published_at = None
            if request.form.get('published_at'):
                try:
                    published_at = datetime.strptime(request.form.get('published_at'), '%Y-%m-%dT%H:%M')
                except:
                    pass
            
            status = request.form.get('status', 'draft')
            if status == 'published' and not published_at and not post.published_at:
                published_at = datetime.utcnow()
            
            post.title = title
            post.slug = slug
            post.content = content
            post.excerpt = excerpt
            post.status = status
            if published_at:
                post.published_at = published_at
            post.meta_title = request.form.get('meta_title', '').strip() or None
            post.meta_description = request.form.get('meta_description', '').strip() or None
            post.meta_keywords = request.form.get('meta_keywords', '').strip() or None
            
            # Handle categories
            post.categories.clear()
            category_ids = request.form.getlist('categories')
            for category_id in category_ids:
                try:
                    category = BlogCategory.query.get(int(category_id))
                    if category:
                        post.categories.append(category)
                except:
                    pass
            
            # Handle tags
            post.tags.clear()
            tags_input = request.form.get('tags', '').strip()
            if tags_input:
                tag_names = [t.strip() for t in tags_input.split(',') if t.strip()]
                for tag_name in tag_names:
                    tag_slug = generate_slug(tag_name)
                    tag = BlogTag.query.filter_by(slug=tag_slug).first()
                    if not tag:
                        tag = BlogTag(name=tag_name, slug=tag_slug)
                        db.session.add(tag)
                        db.session.flush()
                    post.tags.append(tag)
            
            db.session.commit()
            flash('Blog post updated successfully!', 'success')
            return redirect(url_for('blogs.list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating blog post: {str(e)}', 'error')
            return render_template('blogs/form.html',
                                 post=post,
                                 categories=get_all_categories(),
                                 tags=get_all_tags())
    
    # Prepare tags string for form
    tags_string = ', '.join([tag.name for tag in post.tags])
    
    return render_template('blogs/form.html',
                         post=post,
                         categories=get_all_categories(),
                         tags=get_all_tags(),
                         tags_string=tags_string)


@blogs.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Delete blog post"""
    post = BlogPost.query.get_or_404(id)
    
    try:
        # Delete featured image if exists
        if post.featured_image:
            try:
                delete_file_local(post.featured_image)
            except:
                pass
        
        db.session.delete(post)
        db.session.commit()
        flash('Blog post deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting blog post: {str(e)}', 'error')
    
    return redirect(url_for('blogs.list'))


@blogs.route('/import', methods=['GET', 'POST'])
@login_required
def import_posts():
    """WordPress XML import page"""
    if request.method == 'POST':
        if 'xml_file' not in request.files:
            flash('Please select a file to import.', 'error')
            return render_template('blogs/import.html')
        
        file = request.files['xml_file']
        if file.filename == '':
            flash('Please select a file to import.', 'error')
            return render_template('blogs/import.html')
        
        if not file.filename.endswith('.xml'):
            flash('Please upload a valid XML file.', 'error')
            return render_template('blogs/import.html')
        
        # Import options
        skip_existing = request.form.get('skip_existing') == 'on'
        update_existing = request.form.get('update_existing') == 'on'
        
        try:
            from utils.wordpress_import import import_wordpress_xml
            result = import_wordpress_xml(file, skip_existing=skip_existing, update_existing=update_existing)
            
            flash(f'Import completed! Created: {result["created"]}, Updated: {result["updated"]}, Skipped: {result["skipped"]}, Errors: {result["errors"]}', 'success')
            return render_template('blogs/import.html', import_result=result)
        except Exception as e:
            flash(f'Error importing file: {str(e)}', 'error')
            return render_template('blogs/import.html')
    
    return render_template('blogs/import.html')


@blogs.route('/categories', methods=['GET', 'POST'])
@login_required
def manage_categories():
    """Manage blog categories"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Category name is required.', 'error')
            return render_template('blogs/categories.html', categories=get_all_categories())
        
        slug = request.form.get('slug', '').strip() or generate_slug(name)
        
        # Check if slug exists
        if BlogCategory.query.filter_by(slug=slug).first():
            slug = f"{slug}-{int(datetime.now().timestamp())}"
        
        category = BlogCategory(
            name=name,
            slug=slug,
            description=request.form.get('description', '').strip() or None,
            parent_id=int(request.form.get('parent_id')) if request.form.get('parent_id') else None
        )
        
        db.session.add(category)
        db.session.commit()
        flash('Category created successfully!', 'success')
        return redirect(url_for('blogs.manage_categories'))
    
    return render_template('blogs/categories.html', categories=get_all_categories())


def get_all_categories():
    """Get all blog categories"""
    return BlogCategory.query.order_by(BlogCategory.name).all()


def get_all_tags():
    """Get all blog tags"""
    return BlogTag.query.order_by(BlogTag.name).all()

