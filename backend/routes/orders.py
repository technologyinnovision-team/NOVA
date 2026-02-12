from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash
from models.order import Order, OrderItem
from models.product import Product, ProductVariation
from models.customer import Customer
from models import db
from models.setting import Setting
from utils.permissions import login_required
from utils.email import send_email, send_email_async
from sqlalchemy.orm import joinedload
import random
import string

orders = Blueprint('orders', __name__, url_prefix='/admin/orders')

@orders.route('/')
@login_required
def list():
    """Order listing page with customer relationships"""
    # Eagerly load customer relationship to avoid N+1 queries
    orders_list = Order.query.options(
        joinedload(Order.customer)
    ).order_by(Order.created_at.desc()).limit(100).all()
    return render_template('orders/list.html', orders=orders_list)

@orders.route('/create', methods=['GET', 'POST'])
@login_required
def create_order():
    """Create new order manually"""
    if request.method == 'GET':
        return render_template('orders/create.html')
    
    try:
        # Generate unique order number
        order_number = 'ORD-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        while Order.query.filter_by(order_number=order_number).first():
            order_number = 'ORD-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        # Get form data
        customer_email = request.form.get('customer_email')
        phone = request.form.get('phone')
        payment_method = request.form.get('payment_method')
        status = request.form.get('status', 'pending')
        
        # Build billing address
        billing_address = {
            'first_name': request.form.get('billing_first_name'),
            'last_name': request.form.get('billing_last_name'),
            'email': customer_email,
            'phone': phone,
            'address': request.form.get('billing_address'),
            'city': request.form.get('billing_city'),
            'state': request.form.get('billing_state'),
            'zipCode': request.form.get('billing_zipcode'),
            'country': request.form.get('billing_country')
        }
        
        # Use billing as shipping for manual orders
        shipping_address = billing_address.copy()
        
        # Parse order items from form
        items_data = {}
        for key in request.form.keys():
            if key.startswith('items['):
                # Parse items[1][product_id] format
                parts = key.replace('items[', '').replace(']', '').split('[')
                if len(parts) == 2:
                    item_id, field = parts
                    if item_id not in items_data:
                        items_data[item_id] = {}
                    items_data[item_id][field] = request.form.get(key)
        
        # Calculate total and create order items
        total = 0
        order_items = []
        
        for item_id, item_data in items_data.items():
            product_id = int(item_data.get('product_id'))
            quantity = int(item_data.get('quantity', 1))
            price = float(item_data.get('price', 0))
            product_name = item_data.get('product_name')
            
            # Verify product exists
            product = Product.query.get(product_id)
            if not product:
                flash(f'Product ID {product_id} not found', 'error')
                return redirect(url_for('orders.create_order'))
            
            # If product name not provided, use product's name
            if not product_name:
                product_name = product.name
            
            order_item = OrderItem(
                product_id=product_id,
                product_name=product_name,
                quantity=quantity,
                price=price
            )
            order_items.append(order_item)
            total += price * quantity
        
        if not order_items:
            flash('Please add at least one item to the order', 'error')
            return redirect(url_for('orders.create_order'))
        
        # Create order
        order = Order(
            order_number=order_number,
            status=status,
            total=total,
            payment_method=payment_method,
            billing_address=billing_address,
            shipping_address=shipping_address,
            items=order_items
        )
        
        # Stock Deduction for Manual Orders
        for item in order_items:
            product = Product.query.get(item.product_id)
            if product and product.manage_stock:
                product.stock_quantity -= item.quantity
                if product.stock_quantity <= 0:
                    product.stock_quantity = 0
                    product.stock_status = 'out_of_stock'

        db.session.add(order)
        db.session.commit()
        
        flash(f'Order {order_number} created successfully!', 'success')

        # Send admin notification email
        try:
            admin_emails_str = Setting.get('admin_notification_emails', '')
            if admin_emails_str:
                admin_emails = [e.strip() for e in admin_emails_str.split(',') if e.strip()]
                
                admin_subject = f"New Manual Order Created - {order.order_number}"
                admin_body = f"New manual order created.\nOrder Number: {order.order_number}\nTotal: {order.total}\n\nPlease check the admin panel for details."
                
                admin_html = f"""
                <div style="font-family: Arial, sans-serif; padding: 20px;">
                    <h2 style="color: #740c08;">New Manual Order Created</h2>
                    <p><strong>Order Number:</strong> {order.order_number}</p>
                    <p><strong>Customer:</strong> {billing_address.get('first_name', '')} {billing_address.get('last_name', '')}</p>
                    <p><strong>Total:</strong> Rs {order.total:,.2f}</p>
                    <p><strong>Status:</strong> {order.status}</p>
                    <br>
                    <a href="{request.host_url.rstrip('/')}/admin/orders" style="background-color: #333; color: #fff; padding: 10px 20px; text-decoration: none; border-radius: 5px;">View in Admin Panel</a>
                </div>
                """
                
                for admin_email in admin_emails:
                    send_email(admin_email, admin_subject, admin_body, admin_html)
        except Exception as e:
            print(f"Failed to send admin notification: {e}")


        return redirect(url_for('orders.list'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating order: {str(e)}', 'error')
        return redirect(url_for('orders.create_order'))

@orders.route('/<int:order_id>/details')
@login_required
def details(order_id):
    """Get order details with variation information"""
    try:
        order = Order.query.options(
            joinedload(Order.customer),
            joinedload(Order.items)
        ).filter_by(id=order_id).first()
        
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        
        # Build order items with variation details
        items_data = []
        for item in order.items:
            # Get variation details - use stored value or fetch from variation if missing
            variation_details = item.variation_details
            if not variation_details and item.variation_id:
                # Fallback: fetch from variation's attribute_terms
                variation = ProductVariation.query.filter_by(id=item.variation_id).first()
                if variation and variation.attribute_terms:
                    if isinstance(variation.attribute_terms, dict):
                        variation_details = variation.attribute_terms
                    elif isinstance(variation.attribute_terms, str):
                        try:
                            import json
                            variation_details = json.loads(variation.attribute_terms)
                        except:
                            variation_details = {}
                    else:
                        variation_details = {}
            
            item_data = {
                'id': item.id,
                'product_id': item.product_id,
                'variation_id': item.variation_id,
                'variation_details': variation_details if variation_details else {},
                'product_name': item.product_name,
                'quantity': item.quantity,
                'price': float(item.price),
                'subtotal': float(item.price * item.quantity)
            }
            items_data.append(item_data)
        
        # Calculate totals
        subtotal = sum(float(item.price * item.quantity) for item in order.items)
        tax = float(order.tax)
        shipping = float(order.shipping_cost)
        
        # Use stored total
        
        order_data = {
            'id': order.id,
            'order_number': order.order_number,
            'status': order.status,
            'total': float(order.total),
            'subtotal': round(subtotal, 2),
            'tax': round(tax, 2),
            'shipping': round(shipping, 2),
            'payment_method': order.payment_method,
            'payment_transaction_id': order.payment_transaction_id,
            'billing_address': order.billing_address or {},
            'shipping_address': order.shipping_address or {},
            'items': items_data,
            'created_at': order.created_at.strftime('%Y-%m-%d %H:%M:%S') if order.created_at else None,
            'updated_at': order.updated_at.strftime('%Y-%m-%d %H:%M:%S') if order.updated_at else None,
            'customer': {
                'id': order.customer.id if order.customer else None,
                'email': order.customer.email if order.customer else (order.billing_address.get('email', '') if order.billing_address else ''),
                'full_name': order.customer.full_name if order.customer else (
                    f"{order.billing_address.get('first_name', '')} {order.billing_address.get('last_name', '')}".strip()
                    if order.billing_address else 'Guest'
                )
            } if order.customer else {
                'id': None,
                'email': order.billing_address.get('email', '') if order.billing_address else '',
                'full_name': f"{order.billing_address.get('first_name', '')} {order.billing_address.get('last_name', '')}".strip()
                if order.billing_address else 'Guest'
            }
        }
        
        return jsonify(order_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@orders.route('/<int:order_id>/update-status', methods=['POST'])
@login_required
def update_status(order_id):
    """Update order status and send email"""
    try:
        order = Order.query.get_or_404(order_id)
        new_status = request.form.get('status')
        
        if new_status and new_status != order.status:
            old_status = order.status
            order.status = new_status
            db.session.commit()
            
            # Send email notification
            customer_email = order.billing_address.get('email')
            if customer_email:
                # Get base URL for email links
                base_url = request.host_url.rstrip('/')
                
                subject = f"Order Status Update - {order.order_number}"
                body = f"Dear Customer,\n\nYour order {order.order_number} status has been updated from {old_status} to {new_status}.\n\nThank you for shopping with us!"
                
                # Order items HTML generation
                items_html = ""
                for item in order.items:
                    items_html += f"""
                    <tr>
                        <td style="padding: 12px 0; border-bottom: 1px solid #eee; color: #444;">{item.product_name} <span style="color: #888; font-size: 12px;">x {item.quantity}</span></td>
                        <td style="padding: 12px 0; border-bottom: 1px solid #eee; text-align: right; color: #444;">Rs {item.price * item.quantity:,.2f}</td>
                    </tr>
                    """

                # Status colors
                status_bg = '#1a1a1a'
                if new_status == 'pending': status_bg = '#f59e0b'
                elif new_status == 'processing': status_bg = '#3b82f6'
                elif new_status == 'completed': status_bg = '#10b981'
                elif new_status == 'cancelled': status_bg = '#ef4444'

                html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Order Status Update</title>
                </head>
                <body style="margin: 0; padding: 0; background-color: #f4f4f4; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="min-width: 100%;">
                        <tr>
                            <td align="center" style="padding: 30px 15px;">
                                <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
                                    
                                    <!-- Header -->
                                    <tr>
                                        <td align="center" style="padding: 30px; background-color: #1a1a1a;">
                                            <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 600; letter-spacing: 2px;">FAHAD STYLES</h1>
                                        </td>
                                    </tr>

                                    <!-- Status Banner -->
                                    <tr>
                                        <td align="center" style="background-color: {status_bg}; padding: 15px;">
                                            <p style="color: #ffffff; margin: 0; font-weight: bold; font-size: 16px; text-transform: uppercase;">STATUS: {new_status}</p>
                                        </td>
                                    </tr>
                                    
                                    <!-- Main Content -->
                                    <tr>
                                        <td style="padding: 40px 30px;">
                                            <h2 style="color: #1a1a1a; margin-top: 0; margin-bottom: 20px; font-size: 20px;">Order Update</h2>
                                            <p style="color: #555555; line-height: 1.6; margin-bottom: 25px;">
                                                Dear Customer,<br><br>
                                                The status of your order <strong>{order.order_number}</strong> has been updated to <strong style="color: {status_bg}; text-transform: capitalize;">{new_status}</strong>.
                                            </p>

                                            <!-- Tracking Button -->
                                            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom: 30px;">
                                                <tr>
                                                    <td align="center">
                                                        <a href="{base_url}/track-order?order={order.order_number}" style="display: inline-block; background-color: #1a1a1a; color: #ffffff; padding: 14px 30px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 14px; transition: background-color 0.3s;">
                                                            Track Your Order
                                                        </a>
                                                    </td>
                                                </tr>
                                            </table>

                                            <!-- Order Summary -->
                                            <div style="background-color: #f9f9f9; border-radius: 8px; padding: 20px;">
                                                <h3 style="color: #1a1a1a; margin-top: 0; margin-bottom: 15px; font-size: 16px; border-bottom: 1px solid #e5e5e5; padding-bottom: 10px;">Order Summary</h3>
                                                <table width="100%" border="0" cellspacing="0" cellpadding="0" style="font-size: 14px;">
                                                    {items_html}
                                                    <tr>
                                                        <td style="padding-top: 15px; font-weight: bold; color: #1a1a1a;">Total Amount</td>
                                                        <td style="padding-top: 15px; text-align: right; font-weight: bold; color: #1a1a1a;">Rs {order.total:,.2f}</td>
                                                    </tr>
                                                </table>
                                            </div>
                                        </td>
                                    </tr>

                                    <!-- Footer -->
                                    <tr>
                                        <td style="background-color: #f1f1f1; padding: 20px; text-align: center;">
                                            <p style="color: #888888; font-size: 12px; margin: 0; line-height: 1.5;">
                                                Need help? Contact our support team.<br>
                                                &copy; Fahad Styles. All rights reserved.
                                            </p>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                    </table>
                </body>
                </html>
                """
                send_email(customer_email, subject, body, html)
                
            flash(f'Order status updated to {new_status} and email sent.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating order: {str(e)}', 'error')
    
    return redirect(url_for('orders.list'))

