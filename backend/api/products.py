from flask import Blueprint, request, current_app
from sqlalchemy import or_, and_, func, desc, asc
from sqlalchemy.orm import joinedload
from models import db
from models.product import Product, ProductImage, Category, ProductVariation, ProductAttribute
from models.home_section import HomeSection
from models.deal import Deal, DealSlot
from api.middleware import require_api_auth
from api.utils import success_response, error_response
from datetime import datetime
from config import Config

products_bp = Blueprint('products', __name__)

def get_full_image_url(url):
    """Get full image URL with domain"""
    if not url:
        return None
    if url.startswith('http'):
        return url
    
    clean_url = url.strip()
    if not clean_url.startswith('/'):
        clean_url = f'/{clean_url}'
        
    return f"{Config.ASSET_URL}{clean_url}"

def format_product(product, include_variations=False):
    """
    Format product for API response.
    Optimized to minimize lazy loading if eager loading wasn't used, 
    but relies on eager loading for best performance.
    """
    # Optimized image handling
    images = []
    if product.images:
        # Sort in python to avoid extra DB query if already loaded
        sorted_images = sorted(product.images, key=lambda x: (x.image_order, not x.is_primary))
        images = [get_full_image_url(img.image_url) for img in sorted_images]
    
    primary_img = images[0] if images else None
    hover_img = images[1] if len(images) > 1 else primary_img

    # Price calculation
    price_min = None
    price_max = None
    price_range = None
    
    if product.product_type == 'variable':
        if product.variations:
            prices = [
                float(v.sale_price or v.regular_price) 
                for v in product.variations 
                if v.regular_price is not None
            ]
            if prices:
                price_min = min(prices)
                price_max = max(prices)
                if price_min != price_max:
                    price_range = f"{price_min:.2f} - {price_max:.2f}"
    
    if price_min is None:
        price_min = float(product.sale_price or product.regular_price or 0.0)
        price_max = price_min

    # Base dictionary
    formatted = {
        "id": product.id,
        "title": product.title,
        "slug": product.slug,
        "sku": product.sku,
        "name": product.title, # Alias
        "description": product.description or "",
        "short_description": product.short_description or "",
        "price": float(product.regular_price or 0.0),
        "regular_price": float(product.regular_price or 0.0),
        "sale_price": float(product.sale_price) if product.sale_price else None,
        "price_min": price_min,
        "price_max": price_max,
        "price_range": price_range,
        "product_type": product.product_type,
        "on_sale": product.on_sale,
        "featured": product.featured,
        "status": product.status,
        "stock_quantity": product.stock_quantity,
        "stock_status": product.stock_status,
        "manage_stock": product.manage_stock,
        "image": primary_img,
        "hover_image": hover_img,
        "images": images,
        "gallery": images[2:] if len(images) > 2 else [],
        "categories": [{"id": c.id, "name": c.name, "slug": c.slug} for c in product.categories],
        "created_at": product.created_at.isoformat() if product.created_at else None,
        # Shipping / Dimensions
        "weight": float(product.weight) if product.weight else None,
        "dimensions": {
            "length": float(product.length) if product.length else None,
            "width": float(product.width) if product.width else None,
            "height": float(product.height) if product.height else None,
            "unit": product.dimensions_unit
        },
        # Payment / Options
        # Payment / Options
        # Field 'payment_option' removed
        # Field 'advance_payment_amount' removed
        # Field 'disable_cod' removed
        # Field 'sizing_consultation_required' removed
        "available_countries": product.available_countries,
        "gender": product.gender,
    }

    # Stitching Services - Removed

    # Attributes
    formatted["attributes"] = []
    if product.attributes:
        formatted["attributes"] = [
            {
                "id": attr.id,
                "name": attr.name,
                "label": attr.name,
                "variation": attr.use_for_variations,
                "visible": attr.visible,
                "options": [t.name for t in attr.terms] if attr.terms else []
            }
            for attr in product.attributes
        ]

    # Deal logic
    if product.product_type == 'deal' and product.deal:
        deal = product.deal
        formatted["deal"] = {
            "id": deal.id,
            "slots": [
                {
                    "id": slot.id,
                    "title": slot.title,
                    "order": slot.slot_order,
                    "required_quantity": slot.required_quantity,

                    "allowed_categories": [{"id": c.id, "name": c.name} for c in slot.allowed_categories],
                    "allowed_products": [{"id": p.id, "name": p.title} for p in slot.allowed_products]
                }
                for slot in deal.slots
            ]
        }

    # Variations
    if include_variations and product.variations:
        formatted["variations"] = [
            {
                "id": v.id,
                "sku": v.sku,
                "price": float(v.regular_price or 0.0),
                "regular_price": float(v.regular_price or 0.0),
                "sale_price": float(v.sale_price) if v.sale_price else None,
                "stock_quantity": v.stock_quantity,
                "stock_status": v.stock_status,
                "image": get_full_image_url(v.image_url),
                "attributes": v.attribute_terms,
                "weight": float(v.weight) if v.weight else None,
                "dimensions": {
                    "length": float(v.length) if v.length else None,
                    "width": float(v.width) if v.width else None,
                    "height": float(v.height) if v.height else None,
                    "unit": v.dimensions_unit
                } if (v.length or v.width or v.height) else None,
            }
            for v in product.variations
        ]

    return formatted

def base_product_query():
    """Return a base query with optimizations"""
    return Product.query.filter(
        Product.status.in_(['published', 'coming_soon'])
    ).options(
        joinedload(Product.images),
        joinedload(Product.categories),
        joinedload(Product.variations),
        joinedload(Product.attributes),
        joinedload(Product.attributes)
    )

@products_bp.route('/home', methods=['GET'])
@require_api_auth(optional=False)
def get_home_data():
    """
    Get all home page data.
    
    Returns structured data for the home page, including dynamic sections configured in the admin panel.
    """
    try:
        # Pre-fetch sections
        sections = HomeSection.query.filter_by(is_active=True).order_by(HomeSection.display_order.asc()).all()
        
        dynamic_sections = []
        seen_ids = set()

        for section in sections:
            limit = section.item_limit or 12
            query = base_product_query()
            
            # Apply Section Filters
            if section.section_type == 'category' and section.category_id:
                query = query.filter(Product.categories.any(Category.id == section.category_id))
            elif section.section_type == 'new_arrivals':
                # Latest products, maybe featured
                pass # Defaults to sorting by created_at desc
            elif section.section_type == 'sale':
                query = query.filter(Product.on_sale == True)
            elif section.section_type == 'best_selling':
                query = query.order_by(Product.featured.desc()) # Mock best selling
            elif section.section_type == 'deals':
                query = query.filter(Product.product_type == 'deal')

            # Default Sort
            query = query.order_by(Product.created_at.desc()).limit(limit)
            
            products_list = query.all()
            formatted_products = []
            for p in products_list:
                if p.id not in seen_ids:
                    seen_ids.add(p.id)
                    formatted_products.append(format_product(p))
            
            if formatted_products:
                dynamic_sections.append({
                    "id": f"section_{section.id}",
                    "title": section.title,
                    "subtitle": section.subtitle,
                    "type": section.section_type,
                    "products": formatted_products,
                    "link_type": section.section_type,
                    "link_id": section.category_id if section.section_type == 'category' else None
                })
        
        # Fallback if no sections
        if not dynamic_sections:
            # Create default 'New Arrivals'
            latest = base_product_query().order_by(Product.created_at.desc()).limit(12).all()
            if latest:
                dynamic_sections.append({
                    "id": "default_new",
                    "title": "New Arrivals",
                    "subtitle": "Check out our latest collection",
                    "type": "new_arrivals",
                    "products": [format_product(p) for p in latest]
                })

        return success_response({
            "sections": dynamic_sections,
            "meta": {
                "total_sections": len(dynamic_sections),
                "timestamp": datetime.utcnow().isoformat()
            }
        })

    except Exception as e:
        current_app.logger.error(f"Home Data Error: {str(e)}")
        return error_response(str(e), "INTERNAL_ERROR", 500)

@products_bp.route('/detail', methods=['GET'])
@require_api_auth(optional=False)
def get_product_detail():
    """
    Get full product details.
    
    Query Params:
        id (int): Product ID
        slug (str): Product Slug
    """
    try:
        product_id = request.args.get('id')
        slug = request.args.get('slug')
        
        query = base_product_query()
        product = None
        
        if product_id:
            product = query.filter(Product.id == int(product_id)).first()
        elif slug:
            product = query.filter(Product.slug == slug).first()
            
        if not product:
            return error_response("Product not found", "NOT_FOUND", 404)
            
        # Related Products
        related = []
        if product.categories:
            cat_ids = [c.id for c in product.categories]
            related_query = base_product_query().filter(
                Product.id != product.id,
                Product.categories.any(Category.id.in_(cat_ids))
            ).limit(4)
            related = [format_product(p) for p in related_query.all()]
            
        return success_response({
            "product": format_product(product, include_variations=True),
            "related_products": related
        })
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@products_bp.route('/collections', methods=['GET'])
@require_api_auth(optional=False)
def get_collections():
    """
    Get filtered product collections.
    
    Query Params:
        page, per_page, search, min_price, max_price, sort, featured, on_sale, category_id
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 12, type=int), 100)
        search = request.args.get('search', '').strip()
        min_price = request.args.get('min_price', type=float)
        max_price = request.args.get('max_price', type=float)
        sort = request.args.get('sort', 'date')
        category_id = request.args.get('category_id', type=int)
        
        query = base_product_query()
        
        if category_id:
            query = query.filter(Product.categories.any(Category.id == category_id))
            
        if search:
            query = query.filter(or_(
                Product.title.ilike(f'%{search}%'),
                Product.sku.ilike(f'%{search}%'),
                Product.description.ilike(f'%{search}%')
            ))
            
        if min_price: query = query.filter(Product.regular_price >= min_price)
        if max_price: query = query.filter(Product.regular_price <= max_price)
        
        if sort == 'price_asc': query = query.order_by(Product.regular_price.asc())
        elif sort == 'price_desc': query = query.order_by(Product.regular_price.desc())
        elif sort == 'name': query = query.order_by(Product.title.asc())
        else: query = query.order_by(Product.created_at.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return success_response({
            "products": [format_product(p) for p in pagination.items],
            "pagination": {
                "current_page": page,
                "total_pages": pagination.pages,
                "total_items": pagination.total,
                "per_page": per_page
            }
        })
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@products_bp.route('/<int:id>', methods=['GET'])
@require_api_auth(optional=False)
def get_by_id(id):
    """Get product by ID"""
    product = base_product_query().filter(Product.id == id).first()
    if not product:
        return error_response("Product not found", "NOT_FOUND", 404)
    return success_response(format_product(product, include_variations=True))
