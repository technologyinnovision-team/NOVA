from flask import Blueprint, request, current_app, g
from models import db
from models.order import Order, OrderItem
from models.customer import Customer
from models.product import Product, ProductVariation
from models.coupon import Coupon
from models.shipping import ShippingMethod
from api.middleware import require_api_auth
from api.utils import success_response, error_response
from datetime import datetime
import random
import string
import logging
from sqlalchemy.exc import IntegrityError

orders_bp = Blueprint('orders', __name__)

def generate_order_number():
    """Generate unique order number: ORD-YYYYMMDD-XXXXXX"""
    timestamp = datetime.utcnow().strftime('%Y%m%d')
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f'ORD-{timestamp}-{random_part}'

def calculate_totals(items, shipping_method_id=None, coupon_code=None, allow_price_override=False):
    """
    Calculate order totals server-side.
    Returns: (subtotal, shipping, tax, discount, total, processed_items)
    """
    subtotal = 0.0
    processed_items = []
    
    for item in items:
        product_id = item.get('product_id')
        variation_id = item.get('variation_id')
        quantity = int(item.get('quantity', 1))
        
        if quantity < 1: continue
            
        product = Product.query.get(product_id)
        if not product: continue
            
        # Determine base price
        price = float(product.sale_price or product.regular_price or 0)
        variation_details = None
        
        if variation_id:
            variation = ProductVariation.query.get(variation_id)
            if variation:
                price = float(variation.sale_price or variation.regular_price or 0)
                variation_details = variation.attribute_terms
        
        # Override price if allowed and provided
        if allow_price_override and 'price' in item:
            try:
                price = float(item['price'])
            except (ValueError, TypeError):
                pass # Fallback to DB price

        effective_price = price
        
        line_total = effective_price * quantity
        subtotal += line_total
        
        processed_items.append({
            'product': product,
            'variation_id': variation_id,
            'variation_details': variation_details,
            'quantity': quantity,
            'price': price,
            'product_name': product.title
        })

    # Shipping
    shipping_cost = 0.0
    if shipping_method_id:
        method = ShippingMethod.query.get(shipping_method_id)
        if method:
            shipping_cost = float(method.cost)

    # Tax (Mock logic - replace with actual tax logic if available)
    tax = 0.0 

    # Coupon
    discount = 0.0
    if coupon_code:
        coupon = Coupon.query.filter_by(code=coupon_code).first()
        if coupon and coupon.is_valid(order_total=subtotal):
            discount = float(coupon.calculate_discount(subtotal))

    total = max(0.0, subtotal + shipping_cost + tax - discount)
    
    return subtotal, shipping_cost, tax, discount, total, processed_items

@orders_bp.route('/', methods=['POST'])
@require_api_auth(optional=False)
def create_order():
    """
    Create a new order.
    
    Body:
        customer_email (str): Required.
        billing (dict): Billing info.
        shipping (dict): Shipping info.
        items (list): List of items.
        payment_method (str): 'stripe', 'cod', etc.
        shipping_method_id (int): Optional.
        coupon_code (str): Optional.
    """
    try:
        data = request.get_json()
        if not data:
            return error_response("Missing JSON body", "INVALID_REQUEST", 400)
            
        email = data.get('customer_email')
        items = data.get('items', [])
        billing = data.get('billing', {})
        shipping = data.get('shipping', billing) # Fallback to billing
        payment_method = data.get('payment_method')
        
        if not email or not items or not payment_method:
            return error_response("Missing required fields (email, items, payment_method)", "MISSING_FIELDS", 400)

        # 1. Calculate Totals
        # Allow price override for Admin (Session) or Master Key
        allow_price_override = False
        if hasattr(g, 'api_key') and (g.api_key == 'SESSION_USER' or g.api_key == 'MASTER'):
            allow_price_override = True

        subtotal, shipping_cost, tax, discount, total, processed_items = calculate_totals(
            items, 
            data.get('shipping_method_id'), 
            data.get('coupon_code'),
            allow_price_override=allow_price_override
        )
        
        if not processed_items:
            return error_response("No valid items found", "INVALID_ITEMS", 400)

        # 2. Find/Create Customer
        customer = Customer.query.filter_by(email=email).first()
        if not customer:
            customer = Customer(
                email=email,
                first_name=billing.get('first_name', ''),
                last_name=billing.get('last_name', ''),
                phone=billing.get('phone', '')
            )
            db.session.add(customer)
            db.session.flush()

        # 3. Create Order
        order_number = generate_order_number()
        # Retry loop for unique number
        for _ in range(5):
            if not Order.query.filter_by(order_number=order_number).first():
                break
            order_number = generate_order_number()

        order = Order(
            customer_id=customer.id,
            order_number=order_number,
            status='pending',
            total=total,
            # subtotal is not a column in Order model
            tax=tax,
            shipping_cost=shipping_cost,
            coupon_discount=discount,
            coupon_code=data.get('coupon_code'),
            payment_method=payment_method,
            billing_address=billing,
            shipping_address=shipping
        )
        db.session.add(order)
        db.session.flush()

        # 4. Add Items & Deduct Stock
        alerts = []
        for p_item in processed_items:
            # Add OrderItem
            order_item = OrderItem(
                order_id=order.id,
                product_id=p_item['product'].id,
                variation_id=p_item['variation_id'],
                variation_details=p_item['variation_details'],
                product_name=p_item['product_name'],
                quantity=p_item['quantity'],
                price=p_item['price']
            )
            db.session.add(order_item)

            # Stock Management - DELEGATED TO FULFILLMENT SERVICE
            # We do NOT deduct global stock here anymore. 
            # FulfillmentService.assign_order will dedecut from POS or Global(Admin) accordingly.
            
            # product = p_item['product']
            # if product.manage_stock:
            #     product.stock_quantity = max(0, product.stock_quantity - p_item['quantity'])
            #     if product.stock_quantity == 0:
            #         product.stock_status = 'out_of_stock'
            #         alerts.append(f"Product out of stock: {product.title}")
            
            # Variation Stock
            # if p_item['variation_id']:
            #     var = ProductVariation.query.get(p_item['variation_id'])
            #     if var and var.manage_stock:
            #         var.stock_quantity = max(0, var.stock_quantity - p_item['quantity'])
            #         if var.stock_quantity == 0:
            #             var.stock_status = 'out_of_stock'

        db.session.commit()

        # 5. Smart Assignment
        try:
            from services.fulfillment_service import FulfillmentService
            success, message = FulfillmentService.assign_order(order.id)
            current_app.logger.info(f"Order {order.order_number} assignment: {message}")
        except Exception as e:
            current_app.logger.error(f"Order assignment failed: {e}")
            # Do not fail the request, just log it. Admin can manually assign later.
        
        # Async: Send Emails (Implementation skipped for now to avoid complexity, but hooks are here)
        # send_order_confirmation(order)
        
        return success_response({
            "order_number": order.order_number,
            "id": order.id,
            "total": total,
            "message": "Order created successfully"
        }, status_code=201)

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Order Create Error: {e}")
        return error_response(str(e), "INTERNAL_ERROR", 500)

@orders_bp.route('/<int:id>', methods=['GET'])
@require_api_auth(optional=False)
def get_order_summary(id):
    """Get order summary by ID"""
    order = Order.query.get(id)
    if not order:
        return error_response("Order not found", "NOT_FOUND", 404)
    return success_response(format_order(order))

@orders_bp.route('/track/<string:number>', methods=['GET'])
@require_api_auth(optional=False)
def track_order(number):
    """Track order by Order Number"""
    order = Order.query.filter_by(order_number=number).first()
    if not order:
        return error_response("Order not found", "NOT_FOUND", 404)
    return success_response(format_order(order))

def format_order(order):
    """Format Order Object"""
    items = []
    for item in order.items:
        items.append({
            "product_name": item.product_name,
            "quantity": item.quantity,
            "price": float(item.price),
            "price": float(item.price),
            "total": float(item.price * item.quantity)
        })

    return {
        "id": order.id,
        "order_number": order.order_number,
        "status": order.status,
        "total": float(order.total),
        "tax": float(order.tax),
        "shipping_cost": float(order.shipping_cost),
        "discount": float(order.coupon_discount or 0),
        "payment_method": order.payment_method,
        "created_at": order.created_at.isoformat(),
        "items": items,
        "shipping_address": order.shipping_address
    }
