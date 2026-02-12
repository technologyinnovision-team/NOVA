from flask import Blueprint, render_template, request, flash, redirect, url_for
from models import db
from models.product import Product, Category
from models.deal import Deal, DealSlot
from utils.permissions import login_required
from datetime import datetime
import json
from utils.upload import upload_file_local

deals_admin_bp = Blueprint('deals_admin', __name__, url_prefix='/admin/deals')

@deals_admin_bp.route('/')
@login_required
def list_deals():
    """List all deals"""
    deals = Deal.query.all()
    return render_template('deals/list.html', deals=deals)

def process_slots(deal, slots_data):
    """Process and save slots from JSON data"""
    if not slots_data:
        return
        
    try:
        slots_list = json.loads(slots_data)
        
        # Keep track of current slot IDs to delete removed ones
        current_slot_ids = [s.id for s in deal.slots]
        updated_slot_ids = []
        
        for index, slot_data in enumerate(slots_list):
            slot_id = slot_data.get('id')
            
            if slot_id and slot_id in current_slot_ids:
                # Update existing
                slot = DealSlot.query.get(slot_id)
                updated_slot_ids.append(slot_id)
            else:
                # Create new
                slot = DealSlot(deal_id=deal.id)
                db.session.add(slot)
            
            slot.title = slot_data.get('title', f'Slot {index+1}')
            slot.slot_order = index
            slot.required_quantity = int(slot_data.get('required_quantity', 1))
            slot.allow_stitching = bool(slot_data.get('allow_stitching', False))
            slot.allow_custom_size = bool(slot_data.get('allow_custom_size', False))
            
            # Handle categories
            cat_ids = slot_data.get('allowed_category_ids', [])
            slot.allowed_categories = [] # Clear first
            for cat_id in cat_ids:
                category = Category.query.get(cat_id)
                if category:
                    slot.allowed_categories.append(category)

            # Handle products
            prod_ids = slot_data.get('allowed_product_ids', [])
            slot.allowed_products = []
            for prod_id in prod_ids:
                product = Product.query.get(prod_id)
                if product:
                    slot.allowed_products.append(product)

        # Delete removed slots
        for old_id in current_slot_ids:
            if old_id not in updated_slot_ids:
                DealSlot.query.filter_by(id=old_id).delete()
                
    except json.JSONDecodeError:
        pass # Ignore malformed json

def serialize_slots(slots):
    """Serialize slots for JSON usage"""
    return [{
        "id": s.id,
        "title": s.title,
        "required_quantity": s.required_quantity,
        "allow_stitching": s.allow_stitching,
        "allow_custom_size": s.allow_custom_size,
        "allowed_categories": [{"id": c.id, "name": c.name} for c in s.allowed_categories],
        "allowed_products": [{"id": p.id, "title": p.title} for p in s.allowed_products]
    } for s in slots]

@deals_admin_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_deal():
    """Create a new deal"""
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            price = request.form.get('price')
            description = request.form.get('description')
            status = request.form.get('status', 'draft')
            slots_data = request.form.get('slots_data')
            
            if not title or not price:
                flash('Title and Price are required', 'error')
                return redirect(url_for('deals_admin.create_deal'))
            
            # Create Product
            slug = title.lower().replace(' ', '-')
            if Product.query.filter_by(slug=slug).first():
                slug = f"{slug}-{int(datetime.utcnow().timestamp())}"
                
            product = Product(
                title=title,
                slug=slug,
                product_type='deal',
                regular_price=price,
                description=description,
                status=status,
                stock_status='in_stock',
                manage_stock=False
            )
            db.session.add(product)
            db.session.flush()
            
            # Process Featured Image
            featured_image = request.files.get('featured_image')
            featured_image_url = None
            if featured_image:
                featured_image_url = upload_file_local(featured_image, folder='deals')
            
            deal = Deal(product_id=product.id, featured_image=featured_image_url)
            db.session.add(deal)
            db.session.flush()
            
            # Process Slots
            process_slots(deal, slots_data)
            
            db.session.commit()
            flash('Deal created successfully', 'success')
            return redirect(url_for('deals_admin.list_deals'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating deal: {str(e)}', 'error')
            return redirect(url_for('deals_admin.create_deal'))
            
    categories_data = [{"id": c.id, "name": c.name} for c in Category.query.all()]
    # Simple product fetch (in real app, use search or pagination)
    products_data = [{"id": p.id, "title": p.title} for p in Product.query.filter(Product.product_type != 'deal').limit(500).all()]
    return render_template('deals/create.html', categories=categories_data, products=products_data, slots_data=[])

@deals_admin_bp.route('/edit/<int:deal_id>', methods=['GET', 'POST'])
@login_required
def edit_deal(deal_id):
    """Edit deal"""
    deal = Deal.query.get_or_404(deal_id)
    
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            price = request.form.get('price')
            description = request.form.get('description')
            status = request.form.get('status')
            slots_data = request.form.get('slots_data')
            
            if not title or not price:
                flash('Title and Price are required', 'error')
                return redirect(url_for('deals_admin.edit_deal', deal_id=deal.id))
            
            # Update Product
            deal.product.title = title
            deal.product.regular_price = price
            deal.product.description = description
            deal.product.status = status
            
            # Process Featured Image
            featured_image = request.files.get('featured_image')
            if featured_image:
                deal.featured_image = upload_file_local(featured_image, folder='deals')
            
            # Process Slots
            process_slots(deal, slots_data)
            
            db.session.commit()
            flash('Deal updated successfully', 'success')
            return redirect(url_for('deals_admin.list_deals'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating deal: {str(e)}', 'error')
            return redirect(url_for('deals_admin.edit_deal', deal_id=deal.id))
            
    categories_data = [{"id": c.id, "name": c.name} for c in Category.query.all()]
    products_data = [{"id": p.id, "title": p.title} for p in Product.query.filter(Product.product_type != 'deal').limit(500).all()]
    serialized_slots = serialize_slots(deal.slots)
    return render_template('deals/create.html', deal=deal, categories=categories_data, products=products_data, slots_data=serialized_slots)
