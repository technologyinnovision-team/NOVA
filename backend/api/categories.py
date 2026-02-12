from flask import Blueprint, request
from sqlalchemy import and_
from models import db
from models.product import Category, Product
from api.utils import success_response, error_response

def format_product_for_list(product):
    """Format product for list response"""
    images = [img.image_url for img in product.images] if product.images else []
    primary_img = None
    if product.images:
        primary = next((img for img in product.images if img.is_primary), None)
        primary_img = primary.image_url if primary else (product.images[0].image_url if product.images else None)
    
    return {
        "id": product.id,
        "title": product.title,
        "slug": product.slug,
        "sku": product.sku,
        "description": product.description or "",
        "short_description": product.short_description or "",
        "price": float(product.regular_price) if product.regular_price else 0.0,
        "regular_price": float(product.regular_price) if product.regular_price else 0.0,
        "sale_price": float(product.sale_price) if product.sale_price else None,
        "on_sale": product.on_sale,
        "featured": product.featured,
        "status": product.status,
        "stock_quantity": product.stock_quantity,
        "stock_status": product.stock_status,
        "image": primary_img or (images[0] if images else None),
        "images": images,
        "gallery": images[1:] if len(images) > 1 else [],
        "categories": [{"id": cat.id, "name": cat.name, "slug": cat.slug} for cat in product.categories],
    }

categories_bp = Blueprint('categories', __name__)

def format_category(category):
    """Format category for API response"""
    # Calculate product count (published products only)
    product_count = 0
    if hasattr(category, 'products'):
        product_count = sum(1 for p in category.products if p.status in ['published', 'coming_soon'])
    
    return {
        "id": category.id,
        "name": category.name,
        "slug": category.slug,
        "description": category.description,
        "image_url": category.image_url,
        "parent_id": category.parent_id,
        "product_count": product_count,
        "children": [format_category(child) for child in category.children] if category.children else []
    }

@categories_bp.route('/', methods=['GET'])
def list_categories():
    """List all categories"""
    try:
        categories = Category.query.all()
        return success_response([format_category(cat) for cat in categories])
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@categories_bp.route('/<int:category_id>', methods=['GET'])
def get_category(category_id):
    """Get category by ID"""
    category = Category.query.get(category_id)
    if not category:
        return error_response("Category not found", "NOT_FOUND", 404)
    return success_response(format_category(category))

@categories_bp.route('/slug/<slug>', methods=['GET'])
def get_category_by_slug(slug):
    """Get category by slug"""
    category = Category.query.filter_by(slug=slug).first()
    if not category:
        return error_response("Category not found", "NOT_FOUND", 404)
    return success_response(format_category(category))

@categories_bp.route('/<int:category_id>/products', methods=['GET'])
def get_category_products(category_id):
    """Get products in category"""
    try:
        category = Category.query.get(category_id)
        if not category:
            return error_response("Category not found", "NOT_FOUND", 404)
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 12, type=int)
        per_page = min(per_page, 50)
        
        query = Product.query.filter(
            and_(
                Product.status == 'published',
                Product.categories.contains(category)
            )
        )
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return success_response({
            "category": format_category(category),
            "products": [format_product_for_list(p) for p in pagination.items],
            "pagination": {
                "total": pagination.total,
                "per_page": per_page,
                "current_page": page,
                "total_pages": pagination.pages
            }
        })
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

