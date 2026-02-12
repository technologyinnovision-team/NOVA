from flask import Blueprint, request, render_template, current_app
from models.setting import Setting
from utils.email import send_email, send_email_async
from models import db
from models.order import Order, OrderItem
from models.deal import Deal
from models.product import Product
from api.utils import success_response, error_response
from datetime import datetime
import uuid

deal_orders_bp = Blueprint('deal_orders', __name__)

@deal_orders_bp.route('/deal', methods=['POST'])
def create_deal_order():
    """Create an order for a deal bundle"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data or 'deal_id' not in data or 'customer' not in data:
            return error_response("Missing required fields", "INVALID_DATA", 400)
        
        deal_id = data.get('deal_id')
        customer_data = data.get('customer')
        notes = data.get('notes', '')
        total = data.get('total', 0)
        slots = data.get('slots', [])
        payment_method = data.get('payment_method', 'cod') 
        
        # Validate deal exists
        deal = Deal.query.get(deal_id)
        if not deal:
            return error_response("Deal not found", "NOT_FOUND", 404)
        
        # Generate order number
        order_number = f"DEAL-{uuid.uuid4().hex[:8].upper()}"
        
        # Prepare shipping address as JSON
        shipping_address = {
            "name": f"{customer_data.get('firstName')} {customer_data.get('lastName')}",
            "email": customer_data.get('email'),
            "phone": customer_data.get('phone'),
            "address": customer_data.get('address'),
            "city": customer_data.get('city'),
            "postal_code": customer_data.get('postalCode', ''),
            "notes": notes
        }
        
        # Create order with proper fields matching the model
        order = Order(
            order_number=order_number,
            total=total,
            status='pending',
            payment_method=payment_method,
            shipping_address=shipping_address,
            billing_address=shipping_address,  # Same as shipping for deals
            is_deal_order=True,
            deal_id=deal_id
        )
        
        # Store deal slot selections as JSON in order deal_data
        order.deal_data = {
            'deal_title': deal.product.title,
            'deal_slots': slots
        }
        
        db.session.add(order)
        db.session.flush()  # Get order ID
        
        # Create Order Items for each selected product in slots
        for slot in slots:
            slot_id = slot.get('slot_id')
            product_ids = slot.get('product_ids', [])
            
            # Find slot info to get title
            slot_info = next((s for s in deal.slots if s.id == slot_id), None)
            slot_title = slot_info.title if slot_info else f"Slot {slot_id}"
            
            for product_id in product_ids:
                product = Product.query.get(product_id)
                if product:
                    # Create order item
                    # Get original price for display (Deal items are priced 0 for calculation, but we want to show value)
                    original_price = float(product.sale_price or product.regular_price or 0)
                    
                    order_item = OrderItem(
                        order_id=order.id,
                        product_id=product.id,
                        product_name=f"{product.title} (Deal: {deal.product.title} - {slot_title})",
                        quantity=1, 
                        price=0, 
                        original_price=original_price,
                        variation_details={"Deal Slot": slot_title}
                    )
                    db.session.add(order_item)
        
        db.session.commit()
        
        return success_response({
            "order_id": order.id,
            "order_number": order.order_number,
            "message": "Deal order placed successfully"
        }, "Order created successfully", 201)
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creating deal order: {str(e)}")  # Log the error
        import traceback
        traceback.print_exc()
        return error_response(str(e), "INTERNAL_ERROR", 500)

    # Send confirmation email
    try:
        # Get base URL for email links
        base_url = request.host_url.rstrip('/')
        
        subject = f"Order Confirmation - {order.order_number}"
        # Simple text body
        body = f"Dear {order.billing_address.get('name', 'Customer')},\n\nThank you for your order! Your order number is {order.order_number}.\nTotal: {order.total}\n\nWe will notify you when your order is shipped.\n\nBest regards,\nFahad Styles Team"
        
        # HTML Body
        html_items = ""
        for item in order.items:
            html_items += f"""
            <div style="border-bottom: 1px solid #eee; padding: 10px 0; display: flex; align-items: center;">
                <div style="flex: 1;">
                    <p style="margin: 0; font-weight: bold; color: #333;">{item.product_name}</p>
                    <p style="margin: 5px 0 0; font-size: 14px; color: #666;">Qty: {item.quantity}</p>
                </div>
                <div style="font-weight: bold; color: #333;">(Deal Item)</div>
            </div>
            """
        
        # Totals for Email
        email_subtotal = float(order.total) # For deals, usually total matches subtotal as there's no tax/shipping calc in this function yet
        
        html_tax_shipping = "" # No tax/shipping in deal_orders.py currently

        html = f"""
        <div style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
            <div style="background-color: #740c08; padding: 30px 20px; text-align: center;">
                <h1 style="color: #ffffff; margin: 0; font-family: 'Playfair Display', serif; letter-spacing: 1px;">Order Confirmed</h1>
            </div>
            
            <div style="padding: 30px;">
                <p style="font-size: 16px; color: #333; line-height: 1.6;">Dear {order.billing_address.get('name', 'Customer')},</p>
                <p style="font-size: 16px; color: #555; line-height: 1.6;">Thank you for shopping with Fahad Styles! Your order has been received and is being processed.</p>
                
                <div style="background-color: #faf5eb; padding: 20px; border-radius: 8px; margin: 25px 0; text-align: center;">
                    <span style="display: block; font-size: 12px; text-transform: uppercase; letter-spacing: 2px; color: #888; margin-bottom: 5px;">Order Number</span>
                    <span style="display: block; font-size: 24px; font-weight: bold; color: #740c08;">{order.order_number}</span>
                </div>

                <h3 style="color: #333; border-bottom: 2px solid #faf5eb; padding-bottom: 10px; margin-top: 30px;">Order Summary</h3>
                {html_items}
                
                <div style="margin-top: 20px; padding-top: 20px; border-top: 2px solid #faf5eb;">
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
        
        send_email_async(shipping_address.get('email'), subject, body, html)
    except Exception as e:
        print(f"Failed to initiate confirmation email: {str(e)}")

    # Send admin notification email
    try:
        admin_emails_str = Setting.get('admin_notification_emails', '')
        if admin_emails_str:
            admin_emails = [e.strip() for e in admin_emails_str.split(',') if e.strip()]
            
            admin_subject = f"New Deal Order Received - {order.order_number}"
            admin_body = f"New deal order received from {order.billing_address.get('name', 'Customer')}.\nOrder Number: {order.order_number}\nTotal: {order.total}\n\nPlease check the admin panel for details."
            
            admin_html = f"""
            <div style="font-family: Arial, sans-serif; padding: 20px;">
                <h2 style="color: #740c08;">New Deal Order Received</h2>
                <p><strong>Order Number:</strong> {order.order_number}</p>
                <p><strong>Customer:</strong> {order.billing_address.get('name', '')}</p>
                <p><strong>Total:</strong> Rs {order.total:,.2f}</p>
                <p><strong>Status:</strong> {order.status}</p>
                <br>
                <a href="{request.host_url.rstrip('/')}/admin/orders" style="background-color: #333; color: #fff; padding: 10px 20px; text-decoration: none; border-radius: 5px;">View in Admin Panel</a>
            </div>
            """
            
            for admin_email in admin_emails:
                send_email_async(admin_email, admin_subject, admin_body, admin_html)
    except Exception as e:
        print(f"Failed to initiate admin notification: {str(e)}")


    return success_response({
        "order_id": order.id,
        "order_number": order.order_number,
        "message": "Deal order placed successfully"
    }, "Order created successfully", 201)
