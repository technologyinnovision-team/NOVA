from flask import Blueprint, request, session
from models import db
from models.order import Order, OrderItem
from models.customer import Customer
from models.product import Product, ProductVariation
from models.setting import Setting

from api.utils import success_response, error_response, validate_request_json, require_api_auth
from datetime import datetime
import random
import string
import traceback
import logging
import uuid
import threading
from utils.email import send_email, send_email_async

checkout_bp = Blueprint('checkout', __name__)

def generate_order_number():
    """Generate unique order number"""
    timestamp = datetime.utcnow().strftime('%Y%m%d')
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f'ORD-{timestamp}-{random_part}'

@checkout_bp.route('/url', methods=['GET'])
def get_checkout_url():
    """Get checkout URL (redirects to checkout page)"""
    try:
        session_id = request.args.get('session_id')
        redirect_url = request.args.get('redirect_url', '/orders/success')
        
        # Return checkout page URL
        from flask import url_for
        checkout_url = f'/checkout?session_id={session_id}&redirect={redirect_url}'
        
        return success_response({
            "checkout_url": checkout_url,
            "success": True
        })
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@checkout_bp.route('/create-order', methods=['POST'])
@require_api_auth
@validate_request_json(['customer_email', 'total'])
def create_order():
    """Create order from checkout"""
    try:
        data = request.get_json()
        print(f"DEBUG: create_order received data: {data}") # Debug log
        customer_email = data.get('customer_email')
        billing = data.get('billing', {})
        
        # Get line items from request or from session cart
        line_items = data.get('line_items', [])
        print(f"DEBUG: line_items from request: {line_items}") # Debug log
        if not line_items:
            # Try to get from session cart
            cart_data = get_cart_from_session()
            print(f"DEBUG: line_items from session: {cart_data.get('items', [])}") # Debug log
            cart_items = cart_data.get('items', [])
            if cart_items:
                # Convert cart items to line items format
                for item in cart_items:
                    product_id = item.get('product_id')
                    variation_id = item.get('variation_id')
                    quantity = item.get('quantity', 1)
                    
                    product = Product.query.get(product_id)
                    if not product:
                        print(f"DEBUG: Product {product_id} not found during session conversion")
                        continue
                    
                    # Get price
                    price = 0.0
                    if variation_id:
                        variation = ProductVariation.query.filter_by(
                            id=variation_id,
                            product_id=product_id
                        ).first()
                        if variation:
                            price = float(variation.sale_price or variation.regular_price or 0)
                    else:
                        price = float(product.sale_price or product.regular_price or 0)
                    
                    line_items.append({
                        'product_id': product_id,
                        'variation_id': variation_id,
                        'quantity': quantity,
                        'price': price,
                        'attributes': item.get('attributes', []),
                        'attributes': item.get('attributes', [])
                    })
        
        print(f"DEBUG: Final line_items to process: {line_items}") # Debug log

        # Safely convert total to float
        try:
            total = float(data.get('total', 0))
        except (ValueError, TypeError):
            print("DEBUG: Invalid total amount")
            return error_response("Invalid total amount", "INVALID_TOTAL_TYPE", 400)
        
        shipping_address = data.get('shipping_address', billing)
        shipping_method_id = data.get('shipping_method_id')
        payment_method = data.get('payment_method')
        coupon_code = data.get('coupon_code', '').strip().upper() if data.get('coupon_code') else None
        
        # Require explicit payment method selection
        if not payment_method:
            print("DEBUG: Missing payment method")
            return error_response("Payment method is required", "MISSING_PAYMENT_METHOD", 400)
        
        # Apply coupon if provided
        coupon_discount = None
        if coupon_code:
            from models.coupon import Coupon
            coupon = Coupon.query.filter_by(code=coupon_code).first()
            if coupon:
                # Get product IDs from line items
                product_ids = [item.get('product_id') for item in line_items if item.get('product_id')]
                # Validate coupon
                is_valid, message = coupon.is_valid(order_total=total, product_ids=product_ids)
                if is_valid:
                    coupon_discount = coupon.calculate_discount(total)
                    total = total - coupon_discount
                    # Apply coupon (increment usage)
                    coupon.apply()
                    db.session.commit()
                else:
                    return error_response(f"Coupon invalid: {message}", "INVALID_COUPON", 400)
            else:
                return error_response("Invalid coupon code", "INVALID_COUPON", 404)
        
        # Validate email
        try:
            from utils.validators import validate_email
            if not validate_email(customer_email):
                print(f"DEBUG: Invalid email (validator): {customer_email}")
                return error_response("Invalid email address", "INVALID_EMAIL", 400)
        except ImportError as e:
            logging.error(f"Failed to import validate_email: {str(e)}")
            # Fallback email validation using basic regex
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, customer_email):
                print(f"DEBUG: Invalid email (fallback regex): {customer_email}")
                return error_response("Invalid email address", "INVALID_EMAIL", 400)
        
        # Calculate totals server-side
        subtotal = 0.0
        final_line_items = []
        
        for item in line_items:
             product_id = item.get('product_id')
             variation_id = item.get('variation_id')
             quantity = int(item.get('quantity', 1))
             
             product = Product.query.get(product_id)
             if not product:
                 continue
                 
             price = 0.0
             if variation_id:
                 variation = ProductVariation.query.filter_by(id=variation_id, product_id=product_id).first()
                 if variation:
                     price = float(variation.sale_price or variation.regular_price or 0)
             else:
                 price = float(product.sale_price or product.regular_price or 0)
             
             item['price'] = price # Enforce DB price
             final_line_items.append(item)
             
             # Calculate item total including stitching
             item_total = price * quantity
             # Match calculate_cart_subtotal logic
             
             effective_price = price
             subtotal += effective_price * quantity
        
        # Use our validated list
        line_items = final_line_items
        
        shipping_cost = calculate_shipping_cost(subtotal, shipping_method_id)
        tax = calculate_tax(subtotal, shipping_cost)
        
        # Calculate final total
        calculated_total = subtotal + shipping_cost + tax
        
        # Apply coupon logic re-verification
        if coupon_discount:
             calculated_total -= coupon_discount
             
        if calculated_total < 0:
             calculated_total = 0.0
             
        # Override total with calculated one
        total = calculated_total
        
        # Find or create customer
        try:
            customer = Customer.query.filter_by(email=customer_email).first()
            if not customer:
                customer = Customer(
                    email=customer_email,
                    first_name=billing.get('first_name', '') or '',
                    last_name=billing.get('last_name', '') or '',
                    phone=billing.get('phone', '') or ''
                )
                db.session.add(customer)
                db.session.flush() # Flush to get ID, but don't commit yet
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error creating/finding customer: {str(e)}\n{traceback.format_exc()}")
            return error_response(f"Failed to create customer: {str(e)}", "CUSTOMER_CREATION_ERROR", 500)
        
        # Generate order number
        order_number = generate_order_number()
        max_attempts = 10
        attempts = 0
        while Order.query.filter_by(order_number=order_number).first() and attempts < max_attempts:
            order_number = generate_order_number()
            attempts += 1
        
        if attempts >= max_attempts:
            return error_response("Failed to generate unique order number", "ORDER_NUMBER_GENERATION_ERROR", 500)
        
        # Validate total is positive
        if total <= 0:
            print(f"DEBUG: Total <= 0: {total}")
            return error_response("Order total must be greater than 0", "INVALID_TOTAL", 400)
        
        # Validate line items exist
        if not line_items or len(line_items) == 0:
            print("DEBUG: Line items empty after all checks")
            return error_response("Order must contain at least one item", "EMPTY_ORDER", 400)
        
        # Create order with complete data
        try:
            # Determine Fulfillment Source & Assignment
            fulfillment_source = 'admin'
            assigned_seller_id = None
            assignment_status = None
            
            # Check if creator is a POS Seller
            from utils.auth import get_current_user
            current_user = get_current_user()
            if current_user and current_user.pos_profile:
                fulfillment_source = 'pos_stock'
                assigned_seller_id = current_user.pos_profile.id
                assignment_status = 'accepted'
                # Generate POS-style order number if preferred, or keep standard?
                # User wants "Perfect", likely wants consistency. 
                # Keeping ORD- is fine, but attribution MUST be correct.

            order = Order(
                customer_id=customer.id,
                order_number=order_number,
                status='pending' if fulfillment_source == 'admin' else 'completed', # POS orders are usually instant
                total=total,
                payment_method=payment_method,
                coupon_code=coupon_code,
                coupon_discount=coupon_discount,
                tax=tax,
                shipping_cost=shipping_cost,
                billing_address={
                    'first_name': billing.get('first_name', '') or '',
                    'last_name': billing.get('last_name', '') or '',
                    'email': billing.get('email', customer_email) or customer_email,
                    'phone': billing.get('phone', '') or '',
                    'address': billing.get('address', '') or '',
                    'city': billing.get('city', '') or '',
                    'state': billing.get('state', '') or '',
                    'zipCode': billing.get('zipCode', '') or '',
                    'country': billing.get('country', 'US') or 'US'
                },
                shipping_address={
                    'first_name': shipping_address.get('first_name', '') or '',
                    'last_name': shipping_address.get('last_name', '') or '',
                    'email': shipping_address.get('email', customer_email) or customer_email,
                    'phone': shipping_address.get('phone', '') or '',
                    'address': shipping_address.get('address', '') or '',
                    'city': shipping_address.get('city', '') or '',
                    'state': shipping_address.get('state', '') or '',
                    'zipCode': shipping_address.get('zipCode', '') or '',
                    'country': shipping_address.get('country', 'US') or 'US'
                },
                fulfillment_source=fulfillment_source,
                assigned_seller_id=assigned_seller_id,
                assignment_status=assignment_status
            )
            db.session.add(order)
            db.session.flush()
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error creating order: {str(e)}\n{traceback.format_exc()}")
            return error_response(f"Failed to create order: {str(e)}", "ORDER_CREATION_ERROR", 500)
        
        # Add order items
        valid_items_added = 0
        for item in line_items:
            try:
                product_id = item.get('product_id')
                if not product_id:
                    logging.warning(f"Skipping item without product_id: {item}")
                    continue
                
                variation_id = item.get('variation_id')
                quantity = item.get('quantity', 1)
                try:
                    quantity = int(quantity)
                    if quantity <= 0:
                        logging.warning(f"Skipping item with invalid quantity: {quantity}")
                        continue
                except (ValueError, TypeError):
                    logging.warning(f"Skipping item with invalid quantity: {item.get('quantity')}")
                    continue
                
                try:
                    price = float(item.get('price', 0))
                    if price < 0:
                        logging.warning(f"Skipping item with negative price: {price}")
                        continue
                except (ValueError, TypeError):
                    logging.warning(f"Skipping item with invalid price: {item.get('price')}")
                    continue
                
                attributes = item.get('attributes', [])  # Get variation attributes from line item
                
                # Verify product exists
                product = Product.query.get(product_id)
                if not product:
                    logging.warning(f"Product not found: {product_id}")
                    continue
                
                # Verify variation if provided and get variation details
                variation_details = None
                variation = None
                if variation_id:
                    variation = ProductVariation.query.filter_by(
                        id=variation_id,
                        product_id=product_id
                    ).first()
                    if not variation:
                        logging.warning(f"Variation not found: {variation_id} for product {product_id}")
                        continue
                    
                    # Extract variation attributes - prioritize passed attributes, then variation's attribute_terms
                    if attributes and len(attributes) > 0:
                        # Convert attributes array to dictionary format
                        # Format: [{"name": "Color", "option": "Silver"}, {"name": "Size", "option": "Medium"}]
                        variation_details = {}
                        for attr in attributes:
                            if isinstance(attr, dict) and 'name' in attr and 'option' in attr:
                                variation_details[attr['name']] = attr['option']
                            elif isinstance(attr, dict) and len(attr) > 0:
                                # Handle case where attribute might be in different format
                                for key, value in attr.items():
                                    if key != 'name' and key != 'option':
                                        variation_details[key] = str(value)
                        # Only set variation_details if we have valid attributes
                        if not variation_details:
                            variation_details = None
                    
                    # Fallback: use variation's stored attribute_terms (from database)
                    if not variation_details and hasattr(variation, 'attribute_terms') and variation.attribute_terms:
                        if isinstance(variation.attribute_terms, dict):
                            variation_details = variation.attribute_terms if variation.attribute_terms else None
                        elif isinstance(variation.attribute_terms, str):
                            try:
                                import json
                                parsed = json.loads(variation.attribute_terms)
                                variation_details = parsed if parsed else None
                            except:
                                variation_details = None
                    # Also try 'attributes' field as fallback (for compatibility)
                    elif not variation_details and hasattr(variation, 'attributes') and variation.attributes:
                        if isinstance(variation.attributes, dict):
                            variation_details = variation.attributes if variation.attributes else None
                        elif isinstance(variation.attributes, str):
                            try:
                                import json
                                parsed = json.loads(variation.attributes)
                                variation_details = parsed if parsed else None
                            except:
                                variation_details = None
                
                # Get product name
                product_name = getattr(product, 'title', '') or getattr(product, 'name', '') or 'Unknown Product'

                # Enforce price from database
                if variation:
                    price = float(variation.sale_price or variation.regular_price or 0)
                else:
                    price = float(product.sale_price or product.regular_price or 0)
                


                order_item = OrderItem(
                    order_id=order.id,
                    product_id=product_id,
                    variation_id=variation_id if variation_id else None,
                    variation_details=variation_details,
                    product_name=product_name,
                    quantity=quantity,
                    price=price
                )
                db.session.add(order_item)
                valid_items_added += 1
            except Exception as e:
                logging.error(f"Error processing order item: {str(e)}\n{traceback.format_exc()}")
                continue
        
        # Ensure at least one valid item was added
        if valid_items_added == 0:
            db.session.rollback()
            print("DEBUG: valid_items_added is 0")
            return error_response("No valid items found in order", "NO_VALID_ITEMS", 400)
        
        # Order Assignment & Stock Logic
        # Try to assign to POS or fallback to Admin
        try:
            from services.fulfillment_service import FulfillmentService
            success, message = FulfillmentService.assign_order(order.id)
            if not success:
               logging.error(f"Order assignment failed for order {order.order_number}: {message}")
               # If assignment fails completely, we should probably still allow the order but flag it?
               # For now, let's assume if assign_order fails (exception), we log it.
               # But if it returns false (e.g. order not found), that's weird here.
               pass
        except Exception as e:
            logging.error(f"Error during order assignment: {str(e)}")
            # We don't rollback the order creation, but we need to ensure admin sees this.
            # Order status is 'pending', so admin will see it.
            pass
            
        # Old Manual Stock Deduction Removed - now handled by FulfillmentService

        db.session.commit()

        # Handle Out of Stock Alerts (Async)
        if out_of_stock_alerts:
            try:
                alert_subject = "Out of Stock Alert"
                alert_body = "The following items have gone Out of Stock:\n\n" + "\n".join(out_of_stock_alerts)
                
                # Notify Admin via Email
                admin_emails_str = Setting.get('admin_notification_emails', '')
                if admin_emails_str:
                    admin_emails = [e.strip() for e in admin_emails_str.split(',') if e.strip()]
                    for admin_email in admin_emails:
                        send_email_async(admin_email, alert_subject, alert_body, f"<pre>{alert_body}</pre>")
                
            except Exception as e:
                logging.error(f"Failed to send stock alerts: {e}")

        # Send confirmation email
        try:
            # Get base URL for email links
            base_url = request.host_url.rstrip('/')
            
            subject = f"Order Confirmation - {order.order_number}"
            # Simple text body
            body = f"Dear {order.billing_address.get('first_name', 'Customer')},\n\nThank you for your order! Your order number is {order.order_number}.\nTotal: {order.total}\n\nWe will notify you when your order is shipped.\n\nBest regards,\nFahad Styles Team"
            
            # HTML Body
            html_items = ""
            for item in order.items:
                # Prepare stitching text if applicable


                html_items += f"""
                <div style="border-bottom: 1px solid #eee; padding: 10px 0; display: flex; align-items: center;">
                    <div style="flex: 1;">
                        <p style="margin: 0; font-weight: bold; color: #333;">{item.product_name}</p>
                        <p style="margin: 5px 0 0; font-size: 14px; color: #666;">Qty: {item.quantity}</p>

                    </div>
                    <div style="font-weight: bold; color: #333;">Rs {float(item.price) * item.quantity:,.2f}</div>
                </div>
                """
            
            # Corrected Totals Logic for Email
            email_subtotal = float(order.total) - float(order.tax) - float(order.shipping_cost)
            # Ensure subtotal is not negative due to floating point
            if email_subtotal < 0: email_subtotal = 0.0

            html_tax_shipping = f"""
            <div style="display: flex; justify-content: space-between; margin-bottom: 5px; color: #666; font-size: 14px;">
                <span>Tax</span>
                <span>Rs {order.tax:,.2f}</span>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 5px; color: #666; font-size: 14px;">
                <span>Shipping</span>
                <span>Rs {order.shipping_cost:,.2f}</span>
            </div>
            """


            html = f"""
            <div style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
                <div style="background-color: #740c08; padding: 30px 20px; text-align: center;">
                    <h1 style="color: #ffffff; margin: 0; font-family: 'Playfair Display', serif; letter-spacing: 1px;">Order Confirmed</h1>
                </div>
                
                <div style="padding: 30px;">
                    <p style="font-size: 16px; color: #333; line-height: 1.6;">Dear {order.billing_address.get('first_name', 'Customer')},</p>
                    <p style="font-size: 16px; color: #555; line-height: 1.6;">Thank you for shopping with Fahad Styles! Your order has been received and is being processed.</p>
                    
                    <div style="background-color: #faf5eb; padding: 20px; border-radius: 8px; margin: 25px 0; text-align: center;">
                        <span style="display: block; font-size: 12px; text-transform: uppercase; letter-spacing: 2px; color: #888; margin-bottom: 5px;">Order Number</span>
                        <span style="display: block; font-size: 24px; font-weight: bold; color: #740c08;">{order.order_number}</span>
                    </div>

                    <h3 style="color: #333; border-bottom: 2px solid #faf5eb; padding-bottom: 10px; margin-top: 30px;">Order Summary</h3>
                    {html_items}
                    
                    <div style="margin-top: 20px; padding-top: 20px; border-top: 2px solid #faf5eb;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                            <span style="color: #666;">Subtotal</span>
                            <span style="font-weight: bold; color: #333;">Rs {email_subtotal:,.2f}</span>
                        </div>
                        {html_tax_shipping}
                         
                        <div style="display: flex; justify-content: space-between; font-size: 18px; margin-top: 15px; padding-top: 15px; border-top: 1px solid #eee;">
                            <span style="font-weight: bold; color: #333;">Total</span>
                            <span style="font-weight: bold; color: #740c08;">Rs {order.total:,.2f}</span>
                        </div>
                    </div>

                    <p style="margin-top: 30px; font-size: 14px; color: #888; text-align: center;">
                        We'll send you another email when your order ships.
                    </p>
                    
                    <div style="text-align: center; margin-top: 40px;">
                        <a href="{base_url}/track-order?order={order.order_number}" style="display: inline-block; background-color: #333; color: #ffffff; padding: 12px 25px; text-decoration: none; border-radius: 4px; font-weight: bold;">Track Order</a>
                    </div>
                </div>
                
                <div style="background-color: #f9f9f9; padding: 20px; text-align: center; font-size: 12px; color: #999;">
                    &copy; {datetime.now().year} Fahad Styles. All rights reserved.
                </div>
            </div>
            """
            
            # Send email asynchronously to avoid blocking
            send_email_async(customer_email, subject, body, html)
            logging.info(f"Order confirmation email initiated for {customer_email}")
        except Exception as e:
            logging.error(f"Failed to initiate confirmation email: {str(e)}")

        # Send admin notification email
        try:
            admin_emails_str = Setting.get('admin_notification_emails', '')
            if admin_emails_str:
                admin_emails = [e.strip() for e in admin_emails_str.split(',') if e.strip()]
                
                admin_subject = f"New Order Received - {order.order_number}"
                admin_body = f"New order received from {order.billing_address.get('first_name', 'Customer')}.\nOrder Number: {order.order_number}\nTotal: {order.total}\n\nPlease check the admin panel for details."
                
                admin_html = f"""
                <div style="font-family: Arial, sans-serif; padding: 20px;">
                    <h2 style="color: #740c08;">New Order Received</h2>
                    <p><strong>Order Number:</strong> {order.order_number}</p>
                    <p><strong>Customer:</strong> {order.billing_address.get('first_name', '')} {order.billing_address.get('last_name', '')}</p>
                    <p><strong>Total:</strong> Rs {order.total:,.2f}</p>
                    <p><strong>Status:</strong> {order.status}</p>
                    <br>
                    <a href="{request.host_url.rstrip('/')}/admin/orders" style="background-color: #333; color: #fff; padding: 10px 20px; text-decoration: none; border-radius: 5px;">View in Admin Panel</a>
                </div>
                """
                
                for admin_email in admin_emails:
                    send_email_async(admin_email, admin_subject, admin_body, admin_html)
                    logging.info(f"Admin notification email initiated for {admin_email}")
        except Exception as e:
            logging.error(f"Failed to initiate admin notification: {str(e)}")


        # Clear cart from session after successful order
        try:
            if 'cart_session_id' in session:
                session_id = session.get('cart_session_id')
                cart_key = f'cart_{session_id}'
                if cart_key in session:
                    session[cart_key] = {'items': [], 'updated_at': str(datetime.utcnow())}
                    session.modified = True
        except Exception as e:
            logging.warning(f"Failed to clear cart after order: {str(e)}")
        
        return success_response({
            "order_id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "total": float(order.total)
        }, "Order created successfully", 201)
        
    except ValueError as e:
        db.session.rollback()
        logging.error(f"ValueError in create_order: {str(e)}\n{traceback.format_exc()}")
        return error_response(f"Invalid value: {str(e)}", "INVALID_VALUE", 400)
    except KeyError as e:
        db.session.rollback()
        logging.error(f"KeyError in create_order: {str(e)}\n{traceback.format_exc()}")
        return error_response(f"Missing required field: {str(e)}", "MISSING_FIELD", 400)
    except Exception as e:
        db.session.rollback()
        error_trace = traceback.format_exc()
        logging.error(f"Error in create_order: {str(e)}\n{error_trace}")
        # In development, include traceback in error response
        error_message = str(e)
        try:
            from flask import current_app
            if current_app.config.get('DEBUG'):
                error_message = f"{str(e)}\n\nTraceback:\n{error_trace}"
        except:
            pass  # If we can't get the app context, just use the error message
        return error_response(error_message, "INTERNAL_ERROR", 500)

@checkout_bp.route('/get-order/<int:order_id>', methods=['GET'])
def get_order(order_id):
    """Get order details by order ID"""
    try:
        order = Order.query.get(order_id)
        if not order:
            return error_response("Order not found", "NOT_FOUND", 404)
        
        return format_order_response(order)
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@checkout_bp.route('/track/<order_number>', methods=['GET'])
def track_order(order_number):
    """Track order by order number"""
    try:
        order = Order.query.filter_by(order_number=order_number).first()
        if not order:
            return error_response("Order not found", "NOT_FOUND", 404)
        
        return format_order_response(order)
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

def format_order_response(order):
    """Format order for API response"""
    try:
        
        # Get order items with product information
        order_items = []
        for item in order.items:
            item_data = {
                "id": item.id,
                "product_id": item.product_id,
                "variation_id": item.variation_id,
                "variation_details": item.variation_details if item.variation_details else None,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "price": float(item.price),
                "subtotal": float(item.price * item.quantity),
                "original_price": float(item.original_price) if hasattr(item, 'original_price') and item.original_price is not None else float(item.price),
                "image": None
            }
            
            # Try to get product image if product exists
            if item.product_id:
                product = Product.query.get(item.product_id)
                if product:
                    item_data["image"] = product.primary_image
                    item_data["slug"] = product.slug
            
            order_items.append(item_data)
        
        # Calculate totals from stored values
        # Note: item.price in database is product price. item.stitching_cost is separate.
        # So subtotal sum should be (price + stitching_cost) * quantity
        subtotal = sum(float(item.price * item.quantity) for item in order.items)
        tax = float(order.tax)
        shipping = float(order.shipping_cost)
        total = float(order.total)
        
        # Verify subtotal against total for sanity, but trust stored values usually
        # subtotal_calc = total - tax - shipping
        
        # Format dates
        created_at_str = order.created_at.strftime('%Y-%m-%d %H:%M:%S') if order.created_at else None
        updated_at_str = order.updated_at.strftime('%Y-%m-%d %H:%M:%S') if order.updated_at else None
        
        # Determine order status timeline
        status_timeline = []
        if order.status == 'pending':
            status_timeline.append({'status': 'pending', 'label': 'Order Placed', 'completed': True, 'date': created_at_str})
        elif order.status == 'processing':
            status_timeline.append({'status': 'pending', 'label': 'Order Placed', 'completed': True, 'date': created_at_str})
            status_timeline.append({'status': 'processing', 'label': 'Processing', 'completed': True, 'date': updated_at_str})
        elif order.status == 'completed':
            status_timeline.append({'status': 'pending', 'label': 'Order Placed', 'completed': True, 'date': created_at_str})
            status_timeline.append({'status': 'processing', 'label': 'Processing', 'completed': True, 'date': updated_at_str})
            status_timeline.append({'status': 'completed', 'label': 'Completed', 'completed': True, 'date': updated_at_str})
        elif order.status == 'cancelled':
            status_timeline.append({'status': 'pending', 'label': 'Order Placed', 'completed': True, 'date': created_at_str})
            status_timeline.append({'status': 'cancelled', 'label': 'Cancelled', 'completed': True, 'date': updated_at_str})
        
        order_data = {
            "id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "total": round(total, 2),
            "subtotal": round(subtotal, 2),
            "tax": round(tax, 2),
            "shipping": round(shipping, 2),
            "shipping_cost": round(shipping, 2),
            "payment_method": order.payment_method,
            "payment_transaction_id": order.payment_transaction_id,
            "billing_address": order.billing_address or {},
            "shipping_address": order.shipping_address or {},
            "items": order_items,
            "created_at": created_at_str,
            "updated_at": updated_at_str,
            "status_timeline": status_timeline,
            "customer": {
                "id": order.customer_id,
                "email": order.billing_address.get('email', '') if order.billing_address else ''
            } if order.customer_id else None
        }
        
        return success_response(order_data)
    except Exception as e:
        logging.error(f"Error formatting order response: {str(e)}\n{traceback.format_exc()}")
        return error_response(str(e), "INTERNAL_ERROR", 500)


def get_cart_from_session():
    """Get cart from session"""
    if 'cart_session_id' not in session:
        return {'items': []}
    session_id = session.get('cart_session_id')
    cart_key = f'cart_{session_id}'
    return session.get(cart_key, {'items': []})

def calculate_cart_subtotal(cart_items):
    """Calculate subtotal from cart items"""
    subtotal = 0.0
    for item in cart_items:
        product_id = item.get('product_id')
        variation_id = item.get('variation_id')
        quantity = item.get('quantity', 1)
        
        product = Product.query.get(product_id)
        if not product:
            continue
        
        price = 0.0
        if variation_id:
            variation = ProductVariation.query.filter_by(
                id=variation_id,
                product_id=product_id
            ).first()
            if variation:
                price = float(variation.sale_price or variation.regular_price or 0)
        else:
            price = float(product.sale_price or product.regular_price or 0)
        


        subtotal += price * quantity
    return round(subtotal, 2)

def calculate_shipping_cost(subtotal, shipping_method_id=None):
    """Calculate shipping cost based on subtotal and method from DB"""
    try:
        from models.shipping import ShippingMethod
        
        # If no method specified, return 0.0 (Free/No Shipping)
        if not shipping_method_id and shipping_method_id != 0:
             return 0.0
             
        # Try to find method by ID (integer) or name/slug (if passed as string/legacy)
        method = None
        if isinstance(shipping_method_id, int) or (isinstance(shipping_method_id, str) and shipping_method_id.isdigit()):
            method = ShippingMethod.query.get(int(shipping_method_id))
        elif isinstance(shipping_method_id, str):
            # Legacy string handling: lookup by method_type
            method = ShippingMethod.query.filter_by(method_type=shipping_method_id, enabled=True).first()
            
        if not method or not method.enabled:
             # Fallback: if valid method not found, return 0 or look for a default
             # This handles the case where frontend might send "flat_rate" as string initially
             if shipping_method_id:
                 logging.warning(f"Shipping method not found or disabled: {shipping_method_id}")
             return 0.0

        # Logic based on method_type
        # flat_rate, free_shipping, etc.
        config = method.config or {}
        
        if method.method_type == 'free_shipping':
            min_order = float(config.get('min_order_amount', 0))
            if subtotal >= min_order:
                return 0.0
            # If not meeting min order, what to do? Usually free shipping isn't selectable if not eligible?
            # Or maybe it falls back to a cost? Assuming 0 for "Free Shipping" type usually.
            return 0.0
            
        elif method.method_type == 'flat_rate':
            # Check for 'cost' or 'amount' (legacy vs new)
            return float(config.get('cost') or config.get('amount') or 0)
            
        # Add other types like weight_based here if needed
        
        return 0.0
    except Exception as e:
        logging.error(f"Error calculating shipping: {e}")
        return 0.0

def calculate_tax(subtotal, shipping=0.0):
    """Calculate tax based on settings"""
    try:
        tax_enabled_val = Setting.get('tax_enabled', default='false')
        tax_enabled = str(tax_enabled_val).lower() == 'true'
        
        if not tax_enabled:
            return 0.0
        
        tax_rate = float(Setting.get('tax_rate', default='0'))
        if tax_rate <= 0:
            return 0.0
        
        # Calculate tax on subtotal (before shipping)
        tax = subtotal * (tax_rate / 100.0)
        return round(tax, 2)
    except:
        return 0.0

@checkout_bp.route('/calculate-totals', methods=['POST'])
def calculate_totals():
    """Calculate cart totals including shipping and tax"""
    try:
        data = request.get_json() or {}
        shipping_method_id = data.get('shipping_method_id')
        coupon_code = data.get('coupon_code', '').strip().upper() if data.get('coupon_code') else None
        
        # Get cart from session
        cart_data = get_cart_from_session()
        cart_items = cart_data.get('items', [])
        
        if not cart_items:
            # Even if empty, return zeros so UI doesn't crash
            return success_response({
                'subtotal': 0,
                'shipping': 0,
                'tax': 0,
                'coupon_discount': 0,
                'total': 0
            })
        
        # Calculate subtotal
        subtotal = calculate_cart_subtotal(cart_items)
        
        # Calculate shipping
        shipping = calculate_shipping_cost(subtotal, shipping_method_id)
        
        # Calculate tax
        tax = calculate_tax(subtotal, shipping)
        
        # Apply coupon if provided
        coupon_discount = 0.0
        if coupon_code:
            from models.coupon import Coupon
            coupon = Coupon.query.filter_by(code=coupon_code).first()
            if coupon:
                product_ids = [item.get('product_id') for item in cart_items if item.get('product_id')]
                is_valid, message = coupon.is_valid(order_total=subtotal, product_ids=product_ids)
                if is_valid:
                    coupon_discount = coupon.calculate_discount(subtotal)
                else:
                    return error_response(f"Coupon invalid: {message}", "INVALID_COUPON", 400)
            else:
                return error_response("Invalid coupon code", "INVALID_COUPON", 404)
        
        # Calculate total
        total = subtotal + shipping + tax - coupon_discount
        if total < 0:
            total = 0.0
        
        response_data = {
            'subtotal': subtotal,
            'shipping': shipping,
            'tax': tax,
            'coupon_discount': coupon_discount,
            'total': round(total, 2)
        }
        
        # DEBUG: Write to log file
        try:
            with open('debug_checkout.log', 'a') as f:
                import datetime
                f.write(f"\n--- {datetime.datetime.now()} ---\n")
                f.write(f"Cart Items: {cart_items}\n")
                f.write(f"Subtotal: {subtotal}\n")
                f.write(f"Shipping Method ID: {shipping_method_id}\n")
                f.write(f"Shipping: {shipping}\n")
                f.write(f"Tax: {tax}\n")
                f.write(f"Coupon Discount: {coupon_discount}\n")
                f.write(f"Total: {total}\n")
                f.write(f"Response Data: {response_data}\n")
        except Exception as log_err:
            print(f"Failed to write debug log: {log_err}")

        print(f"DEBUG: calculate_totals returning: {response_data}")
        return success_response(response_data)
    except Exception as e:
        logging.error(f"Error calculating totals: {str(e)}\n{traceback.format_exc()}")
        return error_response(str(e), "INTERNAL_ERROR", 500)

@checkout_bp.route('/shipping-methods', methods=['GET'])
def get_shipping_methods():
    """Get available shipping methods from DB"""
    try:
        from models.shipping import ShippingMethod
        methods = ShippingMethod.query.filter_by(enabled=True).order_by(ShippingMethod.priority.asc()).all()
        
        response_data = []
        for method in methods:
            config = method.config or {}
            cost = 0.0
            description = ""
            
            if method.method_type == 'flat_rate':
                # Fix: Check for 'amount' as well as 'cost'
                cost = float(config.get('cost') or config.get('amount') or 0)
                description = f"Rs {cost:,.2f}"
            elif method.method_type == 'free_shipping':
                cost = 0.0
                min_order = float(config.get('min_order_amount', 0))
                if min_order > 0:
                    description = f"Free on orders over Rs {min_order:,.0f}"
                else:
                    description = "Free Shipping"
            
            response_data.append({
                "id": str(method.id), # Cast to string for frontend consistency
                "name": method.name,
                "cost": cost,
                "estimated_days": "3-5", # TODO: Add to model/config?
                "description": description
            })
            
        return success_response(response_data)
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@checkout_bp.route('/payment-methods', methods=['GET'])
def get_payment_methods():
    """Get enabled payment methods"""
    try:
        from models.payment import PaymentGateway
        gateways = PaymentGateway.query.filter_by(enabled=True).all()
        
        methods = []
        for g in gateways:
            method_data = {
                "id": g.gateway_name, # stripe, paypal, cod, bank_transfer
                "name": g.gateway_name.replace('_', ' ').title(),
                "enabled": g.enabled
            }
            
            # Custom names
            if g.gateway_name == 'cod':
                method_data['name'] = "Cash on Delivery (COD)"
            elif g.gateway_name == 'bank_transfer':
                method_data['name'] = "Direct Bank Transfer"
                # Include instruction/details for frontend to display
                config = g.config or {}
                method_data['details'] = {
                    'bank_name': config.get('bank_name'),
                    'account_title': config.get('account_title'),
                    'account_number': config.get('account_number'),
                    'iban': config.get('iban'),
                    'instructions': config.get('instructions')
                }
            
            methods.append(method_data)
            
        return success_response(methods)
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)


