from flask import Blueprint, request, jsonify
from models import db
from models.product import Product, Category
from models.deal import Deal, DealSlot, deal_slot_categories, deal_slot_products
from api.utils import success_response, error_response
from datetime import datetime

deals_bp = Blueprint('deals', __name__)

@deals_bp.route('', methods=['GET'])
def get_deals():
    """Get all deals (admin)"""
    try:
        deals = Deal.query.all()
        result = []
        for deal in deals:
            # Get parent product info
            product = deal.product
            if not product:
                continue
                
            result.append({
                "id": deal.id,
                "product_id": product.id,
                "title": product.title,
                "slug": product.slug,
                "description": product.description or "",
                "price": float(product.regular_price) if product.regular_price else 0,
                "price": float(product.regular_price) if product.regular_price else 0,
                "image": deal.featured_image if deal.featured_image else product.primary_image,
                "status": product.status,
                "slots": [{
                    "id": s.id,
                    "title": s.title,
                    "required_quantity": s.required_quantity
                } for s in deal.slots],
                "created_at": deal.created_at.isoformat()
            })
            
        return success_response(result)
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@deals_bp.route('/slug/<slug>', methods=['GET'])
def get_deal_by_slug(slug):
    """Get deal by product slug (for frontend)"""
    try:
        product = Product.query.filter_by(slug=slug, product_type='deal').first()
        if not product:
            return error_response("Deal not found", "NOT_FOUND", 404)
            
        deal = product.deal
        if not deal:
            return error_response("Deal not found", "NOT_FOUND", 404)
        
        # Format slots
        slots_data = []
        for slot in deal.slots:
            slots_data.append({
                "id": slot.id,
                "title": slot.title,
                "order": slot.slot_order,
                "required_quantity": slot.required_quantity,

                "allowed_categories": [{"id": c.id, "name": c.name, "slug": c.slug} for c in slot.allowed_categories],
                "allowed_products": [{"id": p.id, "title": p.title, "slug": p.slug, "price": float(p.regular_price) if p.regular_price else 0, "image": p.primary_image} for p in slot.allowed_products]
            })
            
        return success_response({
            "id": deal.id,
            "product_id": product.id,
            "title": product.title,
            "slug": product.slug,
            "description": product.description or "",
            "price": float(product.regular_price) if product.regular_price else 0,
            "description": product.description or "",
            "price": float(product.regular_price) if product.regular_price else 0,
            "image": deal.featured_image if deal.featured_image else product.primary_image,
            "images": [img.image_url for img in product.images] if product.images else [],
            "status": product.status,
            "slots": slots_data
        })
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@deals_bp.route('/<int:deal_id>', methods=['GET'])
def get_deal(deal_id):
    """Get single deal details"""
    try:
        deal = Deal.query.get(deal_id)
        if not deal:
            return error_response("Deal not found", "NOT_FOUND", 404)
            
        product = deal.product
        
        # Format slots
        slots_data = []
        for slot in deal.slots:
            slots_data.append({
                "id": slot.id,
                "title": slot.title,
                "order": slot.slot_order,
                "required_quantity": slot.required_quantity,

                "allowed_categories": [{"id": c.id, "name": c.name} for c in slot.allowed_categories],
                "allowed_products": [{"id": p.id, "name": p.title} for p in slot.allowed_products]
            })
            
        return success_response({
            "id": deal.id,
            "product_id": product.id,
            "title": product.title,
            "slug": product.slug,
            "description": product.description,
            "description": product.description,
            "price": float(product.regular_price),
            "image": deal.featured_image if deal.featured_image else product.primary_image,
            "sale_price": float(product.sale_price) if product.sale_price else None,
            "status": product.status,
            "slots": slots_data
        })
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@deals_bp.route('', methods=['POST'])
def create_deal():
    """Create a new deal (Product + Deal + Slots)"""
    try:
        data = request.json
        if not data:
            return error_response("No data provided", "INVALID_DATA", 400)
            
        title = data.get('title')
        price = data.get('price')
        slots_data = data.get('slots', [])
        
        if not title or not price:
            return error_response("Title and Price are required", "MISSING_FIELDS", 400)
            
        # 1. Create Product
        # Generate slug
        slug = title.lower().replace(' ', '-')
        # Ensure unique slug
        if Product.query.filter_by(slug=slug).first():
            slug = f"{slug}-{int(datetime.utcnow().timestamp())}"
            
        new_product = Product(
            title=title,
            slug=slug,
            product_type='deal',
            regular_price=price,
            stock_status='in_stock',
            status='draft', # Default to draft
            requires_sizing=False, # Deals might utilize detailed sizing in slots
            manage_stock=False
        )
        db.session.add(new_product)
        db.session.flush() # Get ID
        
        # 2. Create Deal
        new_deal = Deal(product_id=new_product.id)
        db.session.add(new_deal)
        db.session.flush()
        
        # 3. Create Slots
        for idx, slot_data in enumerate(slots_data):
            slot = DealSlot(
                deal_id=new_deal.id,
                title=slot_data.get('title', f'Slot {idx+1}'),
                slot_order=idx,
                required_quantity=slot_data.get('required_quantity', 1),
                # Stitching removed

            )
            
            # Add constraints
            cat_ids = slot_data.get('allowed_category_ids', [])
            if cat_ids:
                categories = Category.query.filter(Category.id.in_(cat_ids)).all()
                slot.allowed_categories.extend(categories)
                
            prod_ids = slot_data.get('allowed_product_ids', [])
            if prod_ids:
                products = Product.query.filter(Product.id.in_(prod_ids)).all()
                slot.allowed_products.extend(products)
                
            db.session.add(slot)
            
        db.session.commit()
        
        return success_response({
            "message": "Deal created successfully",
            "deal_id": new_deal.id,
            "product_id": new_product.id
        })
        
    except Exception as e:
        db.session.rollback()
        return error_response(str(e), "INTERNAL_ERROR", 500)

@deals_bp.route('/<int:deal_id>', methods=['PUT'])
def update_deal(deal_id):
    """Update deal structure"""
    try:
        deal = Deal.query.get(deal_id)
        if not deal:
            return error_response("Deal not found", "NOT_FOUND", 404)
            
        product = deal.product
        data = request.json
        
        # Update product info
        if 'title' in data:
            product.title = data['title']
        if 'price' in data:
            product.regular_price = data['price']
        if 'status' in data:
            product.status = data['status']
        if 'description' in data:
            product.description = data['description']
            
        # Update Slots (Full replacement approach for simplicity)
        if 'slots' in data:
            # Remove old slots
            for slot in deal.slots:
                db.session.delete(slot)
            
            # Add new slots
            for idx, slot_data in enumerate(data['slots']):
                slot = DealSlot(
                    deal_id=deal.id,
                    title=slot_data.get('title', f'Slot {idx+1}'),
                    slot_order=idx,
                    required_quantity=slot_data.get('required_quantity', 1),
                    # Stitching removed

                )
                
                cat_ids = slot_data.get('allowed_category_ids', [])
                if cat_ids:
                    categories = Category.query.filter(Category.id.in_(cat_ids)).all()
                    slot.allowed_categories.extend(categories)
                    
                prod_ids = slot_data.get('allowed_product_ids', [])
                if prod_ids:
                    products = Product.query.filter(Product.id.in_(prod_ids)).all()
                    slot.allowed_products.extend(products)
                    
                db.session.add(slot)
                
        db.session.commit()
        
        return success_response({"message": "Deal updated successfully"})
        
    except Exception as e:
        db.session.rollback()
        return error_response(str(e), "INTERNAL_ERROR", 500)
