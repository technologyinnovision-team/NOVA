from flask import Blueprint, request
from sqlalchemy import or_, desc, asc
from models import db
from models.blog import BlogPost, BlogCategory, BlogTag
from api.utils import success_response, error_response
from datetime import datetime

blogs_bp = Blueprint('blogs', __name__)

def format_blog_post(post, include_content=False):
    """Format blog post for API response"""
    return {
        'id': post.id,
        'title': post.title,
        'slug': post.slug,
        'content': post.content if include_content else None,
        'excerpt': post.excerpt or '',
        'featured_image': post.featured_image,
        'status': post.status,
        'published_at': post.published_at.isoformat() if post.published_at else None,
        'author': {
            'id': post.author.id if post.author else None,
            'username': post.author.username if post.author else 'Unknown',
            'name': post.author.username if post.author else 'Unknown'
        } if post.author else {'id': None, 'username': 'Unknown', 'name': 'Unknown'},
        'categories': [{'id': cat.id, 'name': cat.name, 'slug': cat.slug} for cat in post.categories],
        'tags': [{'id': tag.id, 'name': tag.name, 'slug': tag.slug} for tag in post.tags],
        'created_at': post.created_at.isoformat() if post.created_at else None,
        'updated_at': post.updated_at.isoformat() if post.updated_at else None,
        'meta_title': post.meta_title,
        'meta_description': post.meta_description,
        'meta_keywords': post.meta_keywords
    }

@blogs_bp.route('/blogs', methods=['GET'])
def list_blogs():
    """List blog posts with pagination and filtering"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        per_page = min(per_page, 50)  # Limit max
        search = request.args.get('search', '').strip()
        category = request.args.get('category', '').strip()
        tag = request.args.get('tag', '').strip()
        status = request.args.get('status', 'published')  # Default to published for public API
        
        # Only allow published posts for public API
        if status != 'published':
            status = 'published'
        
        query = BlogPost.query.filter(BlogPost.status == 'published')
        
        # Search filter
        if search:
            query = query.filter(
                or_(
                    BlogPost.title.ilike(f'%{search}%'),
                    BlogPost.content.ilike(f'%{search}%'),
                    BlogPost.excerpt.ilike(f'%{search}%')
                )
            )
        
        # Category filter
        if category:
            try:
                category_id = int(category)
                query = query.join(BlogPost.categories).filter(BlogCategory.id == category_id)
            except:
                category_obj = BlogCategory.query.filter_by(slug=category).first()
                if category_obj:
                    query = query.join(BlogPost.categories).filter(BlogCategory.id == category_obj.id)
        
        # Tag filter
        if tag:
            tag_obj = BlogTag.query.filter_by(slug=tag).first()
            if tag_obj:
                query = query.join(BlogPost.tags).filter(BlogTag.id == tag_obj.id)
        
        # Order by published date (newest first)
        query = query.order_by(desc(BlogPost.published_at), desc(BlogPost.created_at))
        
        # Pagination
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return success_response({
            'posts': [format_blog_post(p) for p in pagination.items],
            'pagination': {
                'total': pagination.total,
                'per_page': per_page,
                'current_page': page,
                'total_pages': pagination.pages,
                'has_more': pagination.has_next
            }
        })
    except Exception as e:
        return error_response(str(e), 'INTERNAL_ERROR', 500)

@blogs_bp.route('/blogs/<slug>', methods=['GET'])
def get_blog_post(slug):
    """Get single blog post by slug"""
    try:
        post = BlogPost.query.filter_by(slug=slug, status='published').first()
        if not post:
            return error_response('Blog post not found', 'NOT_FOUND', 404)
        
        return success_response(format_blog_post(post, include_content=True))
    except Exception as e:
        return error_response(str(e), 'INTERNAL_ERROR', 500)

@blogs_bp.route('/blogs/categories', methods=['GET'])
def list_categories():
    """List all blog categories"""
    try:
        categories = BlogCategory.query.order_by(BlogCategory.name).all()
        return success_response({
            'categories': [{
                'id': cat.id,
                'name': cat.name,
                'slug': cat.slug,
                'description': cat.description,
                'post_count': len(cat.posts) if hasattr(cat, 'posts') else 0
            } for cat in categories]
        })
    except Exception as e:
        return error_response(str(e), 'INTERNAL_ERROR', 500)

@blogs_bp.route('/blogs/tags', methods=['GET'])
def list_tags():
    """List all blog tags"""
    try:
        tags = BlogTag.query.order_by(BlogTag.name).all()
        return success_response({
            'tags': [{
                'id': tag.id,
                'name': tag.name,
                'slug': tag.slug,
                'post_count': len(tag.posts) if hasattr(tag, 'posts') else 0
            } for tag in tags]
        })
    except Exception as e:
        return error_response(str(e), 'INTERNAL_ERROR', 500)

@blogs_bp.route('/blogs/category/<slug>', methods=['GET'])
def get_blogs_by_category(slug):
    """Get blog posts by category slug"""
    try:
        category = BlogCategory.query.filter_by(slug=slug).first()
        if not category:
            return error_response('Category not found', 'NOT_FOUND', 404)
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        per_page = min(per_page, 50)
        
        query = BlogPost.query.filter(
            BlogPost.status == 'published'
        ).join(BlogPost.categories).filter(BlogCategory.id == category.id)
        
        query = query.order_by(desc(BlogPost.published_at), desc(BlogPost.created_at))
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return success_response({
            'category': {
                'id': category.id,
                'name': category.name,
                'slug': category.slug,
                'description': category.description
            },
            'posts': [format_blog_post(p) for p in pagination.items],
            'pagination': {
                'total': pagination.total,
                'per_page': per_page,
                'current_page': page,
                'total_pages': pagination.pages,
                'has_more': pagination.has_next
            }
        })
    except Exception as e:
        return error_response(str(e), 'INTERNAL_ERROR', 500)

