from flask import Blueprint, request, jsonify
from models import db
from models.order import Order
from models.pos import POSSellerProfile, POSInventory
from services.fulfillment_service import FulfillmentService
from utils.permissions import login_required
from datetime import datetime

pos_bp = Blueprint('pos_api', __name__, url_prefix='/api/pos')

@pos_bp.route('/orders/pending', methods=['GET'])
@login_required
def get_pending_orders():
    """
    Get orders assigned to the logged-in POS seller that are pending acceptance.
    """
    # Assuming user.pos_profile exists if they are a POS Seller
    from utils.auth import get_current_user
    user = get_current_user()
    
    if not user or not user.pos_profile:
        return jsonify({'error': 'Unauthorized or not a POS seller'}), 401

    orders = Order.query.filter_by(
        assigned_seller_id=user.pos_profile.id,
        assignment_status='assigned'
    ).all()
    
    # Serialization (simplified)
    data = []
    for o in orders:
        data.append({
            'id': o.id,
            'order_number': o.order_number,
            'total': float(o.total),
            'created_at': o.created_at.isoformat(),
            'expiry': o.assignment_expiry.isoformat() if o.assignment_expiry else None
        })
    
    return jsonify({'orders': data})

@pos_bp.route('/orders/<int:order_id>/accept', methods=['POST'])
@login_required
def accept_order(order_id):
    """
    POS Seller accepts the order.
    """
    from utils.auth import get_current_user
    user = get_current_user()
    if not user or not user.pos_profile:
        return jsonify({'error': 'Unauthorized'}), 401
    
    order = Order.query.get(order_id)
    if not order or order.assigned_seller_id != user.pos_profile.id:
        return jsonify({'error': 'Order not found or not assigned to you'}), 404
        
    if order.assignment_status != 'assigned':
         return jsonify({'error': 'Order is not in pending state'}), 400
         
    try:
        order.assignment_status = 'accepted'
        db.session.commit()
        return jsonify({'message': 'Order accepted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@pos_bp.route('/orders/<int:order_id>/reject', methods=['POST'])
@login_required
def reject_order(order_id):
    """
    POS Seller rejects the order.
    System should immediately re-assign to next seller.
    """
    from utils.auth import get_current_user
    user = get_current_user()
    if not user or not user.pos_profile:
        return jsonify({'error': 'Unauthorized'}), 401
        
    order = Order.query.get(order_id)
    if not order or order.assigned_seller_id != user.pos_profile.id:
        return jsonify({'error': 'Order not found or not assigned to you'}), 404
        
    try:
        # Release Stock
        for item in order.items:
            inventory = POSInventory.query.filter_by(
                seller_id=user.pos_profile.id,
                product_id=item.product_id,
                variation_id=item.variation_id
            ).first()
            if inventory:
                inventory.reserved_quantity -= item.quantity
                if inventory.reserved_quantity < 0: inventory.reserved_quantity = 0

        # Update status to rejected (temporarily, or just log it?)
        # Actually we want assign_order to pick the NEXT one.
        # But assign_order uses assignment_attempts as index.
        # So we just leave assignment_attempts AS IS (it was incremented when assigned).
        # We assume rejection means "Try next".
        
        # We need to mark this specific assignment attempt as failed/rejected?
        # Since we use a simple counter index, simply calling assign_order will pick the NEXT index.
        # We just need to clear the current assignment.
        
        order.assigned_seller_id = None
        order.assignment_status = 'rejected' 
        # But we want to trigger reassignment immediately.
        
        db.session.commit() # Commit the release of stock first
        
        # Trigger Reassignment
        success, msg = FulfillmentService.assign_order(order.id)
        
        return jsonify({'message': 'Order rejected. Reassignment triggered.', 'reassignment_result': msg})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@pos_bp.route('/orders/create', methods=['POST'])
@login_required
def create_order():
    """
    Create a new POS Order (Walk-in Customer)
    Deducts stock from POS Inventory instantly.
    """
    from utils.auth import get_current_user
    user = get_current_user()
    if not user or not user.pos_profile:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    if not data or 'items' not in data:
        return jsonify({'error': 'No items provided'}), 400
        
    try:
        # Calculate totals
        subtotal = 0
        items_db = []
        
        for item in data['items']:
            product_id = item.get('product_id')
            quantity = item.get('quantity', 1)
            variation_id = item.get('variation_id')
            
            # Check Stock in POS Inventory
            inventory = POSInventory.query.filter_by(
                seller_id=user.pos_profile.id,
                product_id=product_id,
                variation_id=variation_id
            ).first()
            
            if not inventory or inventory.quantity < quantity:
                return jsonify({'error': f'Insufficient stock for Product ID {product_id}'}), 400
                
            # Create Order Item (conceptual - we need actual OrderItem logic here if we reuse Order model)
            # Assuming we use the standard Order implementation, we need to populate Order first.
            # But we need price info.
            
            # Fetch Product to get price
            from models.product import Product, ProductVariation
            product = Product.query.get(product_id)
            price = product.regular_price
            if variation_id:
                 var = ProductVariation.query.get(variation_id)
                 if var: price = var.regular_price
            
            # Use override price if allowed/provided? No, stick to system price for now.
            line_total = float(price) * quantity
            subtotal += line_total
            
            # Deduct Stock
            inventory.quantity -= quantity
            
            items_db.append({
                'product_id': product_id,
                'variation_id': variation_id,
                'quantity': quantity,
                'price': price,
                'total': line_total
            })
            
        # Create Order Record
        # Extract Customer Info if provided
        customer_email = data.get('customer_email', user.email)
        
        # Billing
        billing = data.get('billing', {})
        billing_address = {
            'first_name': billing.get('first_name', 'Walk-in'),
            'last_name': billing.get('last_name', 'Customer'),
            'address_1': billing.get('address', ''),
            'city': billing.get('city', ''),
            'state': billing.get('state', ''),
            'postcode': billing.get('zipCode', ''),
            'country': billing.get('country', ''),
            'email': customer_email,
            'phone': billing.get('phone', '')
        }
        
        # Shipping (Default to billing if empty, or specific)
        shipping = data.get('shipping', {})
        shipping_address = {
            'first_name': shipping.get('first_name', billing_address['first_name']),
            'last_name': shipping.get('last_name', billing_address['last_name']),
            'address_1': shipping.get('address', billing_address['address_1']),
            'city': shipping.get('city', billing_address['city']),
            'state': shipping.get('state', billing_address['state']),
            'postcode': shipping.get('zipCode', billing_address['postcode']),
            'country': shipping.get('country', billing_address['country'])
        }

        order = Order(
            order_number=f"POS-{user.pos_profile.id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            # Remove non-existent columns
            # customer_first_name=..., 
            # customer_last_name=...,
            email=customer_email,
            status='completed', # POS orders are instant
            payment_status='paid',
            payment_method=data.get('payment_method', 'cash'),
            subtotal=subtotal,
            total=subtotal, # Tax logic omitted for MVP
            assigned_seller_id=user.pos_profile.id,
            assignment_status='accepted',
            fulfillment_source='pos_stock',
            
            # Save addresses as JSON (Correct way)
            billing_address=billing_address,
            shipping_address=shipping_address
        )
        db.session.add(order)
        db.session.flush()
        
        # Create Order Items
        from models.order import OrderItem
        for item in items_db:
            order_item = OrderItem(
                order_id=order.id,
                product_id=item['product_id'],
                variation_id=item['variation_id'],
                quantity=item['quantity'],
                price=item['price'],
                total=item['total']
            )
            db.session.add(order_item)
            
        db.session.commit()
        
        return jsonify({
            'message': 'Order created successfully',
            'order_id': order.id,
            'order_number': order.order_number,
            'total': subtotal
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@pos_bp.route('/sellers', methods=['GET'])
def get_pos_sellers():
    """
    Get all active POS seller profiles with location data.
    Public endpoint for store locator/map.
    """
    try:
        sellers = POSSellerProfile.query.filter_by(is_active=True).all()
        
        data = []
        for seller in sellers:
            # Only include sellers with valid coordinates or address
            if seller.latitude and seller.longitude:
                data.append({
                    'id': seller.id,
                    'business_name': seller.business_name,
                    'address': {
                        'line1': seller.address_line1,
                        'city': seller.city,
                        'state': seller.state,
                        'zip_code': seller.zip_code,
                        'country': seller.country
                    },
                    'location': {
                        'lat': seller.latitude,
                        'lng': seller.longitude
                    },
                    'auto_accept': seller.auto_accept_orders
                })
        
        return jsonify({'sellers': data})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@pos_bp.route('/simulate-order', methods=['POST'])
@login_required
def simulate_order():
    """
    Internal endpoint to simulate an order from the POS Testing page (Checkout Flow).
    This bypasses API Key auth (uses session) and triggers Fulfillment Service.
    """
    from utils.auth import get_current_user
    user = get_current_user()
    if not user: 
        return jsonify({'error': 'Unauthorized'}), 401
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Missing JSON body'}), 400
            
        items = data.get('items', [])
        email = data.get('customer_email')
        
        if not items or not email:
            return jsonify({'error': 'Missing items or email'}), 400
            
        # 1. Calculate Totals
        from models.product import Product
        
        subtotal = 0.0
        order_items_data = []
        
        for item in items:
            product_id = item.get('product_id')
            quantity = int(item.get('quantity', 1))
            
            product = Product.query.get(product_id)
            if not product: continue
            
            price = float(product.sale_price or product.regular_price or 0)
            
            line_total = price * quantity
            subtotal += line_total
            
            order_items_data.append({
                'product': product,
                'quantity': quantity,
                'price': price,
                'total': line_total,
                'variation_id': None 
            })
            
        if not order_items_data:
             return jsonify({'error': 'No valid products found'}), 400
             
        # 2. Shipping/Billing
        billing = data.get('billing', {})
        shipping = data.get('shipping', billing)
        
        # 3. Create/Find Customer
        from models.customer import Customer
        customer = Customer.query.filter_by(email=email).first()
        if not customer:
            customer = Customer(
                email=email,
                first_name=billing.get('first_name',''),
                last_name=billing.get('last_name',''),
                phone=billing.get('phone','')
            )
            db.session.add(customer)
            db.session.flush()
        else:
            # Update phone/name if missing
            if not customer.phone and billing.get('phone'):
                customer.phone = billing.get('phone')
            if not customer.first_name and billing.get('first_name'):
                customer.first_name = billing.get('first_name')
            if not customer.last_name and billing.get('last_name'):
                 customer.last_name = billing.get('last_name')
            
        # 4. Create Order
        import random, string
        timestamp = datetime.utcnow().strftime('%Y%m%d')
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        order_number = f'TEST-{timestamp}-{random_part}'
        
        order = Order(
            customer_id=customer.id,
            order_number=order_number,
            status='pending',
            total=subtotal,
            # subtotal=subtotal, 
            payment_method=data.get('payment_method', 'cod'),
            shipping_cost=0, # Simplified for test
            tax=0,
            billing_address=billing,
            shipping_address=shipping
        )
        db.session.add(order)
        db.session.flush()
        
        # 5. Add Items
        from models.order import OrderItem
        for idata in order_items_data:
            oi = OrderItem(
                order_id=order.id,
                product_id=idata['product'].id,
                product_name=idata['product'].title,
                quantity=idata['quantity'],
                price=idata['price'],
                # total=idata['total'] 
            )
            db.session.add(oi)
            
        db.session.commit()
        
        # 6. Trigger Assignment
        success, msg = FulfillmentService.assign_order(order.id)
        
        return jsonify({
            'message': 'Order simulated successfully',
            'data': {
                'order_number': order.order_number,
                'id': order.id,
                'total': subtotal,
                'assignment_result': msg
            }
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
