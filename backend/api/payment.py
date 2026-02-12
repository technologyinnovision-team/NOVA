from flask import Blueprint, request
from models import db
from models.payment import PaymentGateway
from models.order import Order
from api.middleware import require_api_auth
from api.utils import success_response, error_response
import stripe
import paypalrestsdk
from sqlalchemy.orm.attributes import flag_modified
import traceback

payment_bp = Blueprint('payment', __name__)

def get_gateway_config(name):
    """Helper to get and configure gateway"""
    gateway = PaymentGateway.query.filter_by(gateway_name=name, enabled=True).first()
    if not gateway:
        return None, "Gateway not available"
    
    # Refresh to ensure latest config
    try:
        db.session.refresh(gateway, ['config'])
    except:
        pass
        
    return gateway, None

@payment_bp.route('/gateways', methods=['GET'])
@require_api_auth(optional=True)
def get_payment_gateways():
    """
    Get available payment gateways.
    Returns public configuration for enabled gateways.
    """
    try:
        gateways = PaymentGateway.query.filter_by(enabled=True).all()
        result = []
        
        for g in gateways:
            info = {
                "id": g.gateway_name,
                "name": g.gateway_name.title(),
                "mode": g.config.get('mode', 'test') if g.config else 'test'
            }
            
            if g.gateway_name == 'stripe':
                info['publishable_key'] = g.config.get('publishable_key')
            elif g.gateway_name == 'paypal':
                info['client_id'] = g.config.get('client_id')
                
            result.append(info)
            
        return success_response(result)
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@payment_bp.route('/stripe/intent', methods=['POST'])
@require_api_auth(optional=False)
def create_payment_intent():
    """
    Create Stripe Payment Intent.
    
    Body:
        amount (float): Amount in dollars/unit.
        currency (str): default 'usd'.
        order_id (int): Related Order ID.
    """
    try:
        data = request.get_json()
        amount = data.get('amount')
        order_id = data.get('order_id')
        currency = data.get('currency', 'usd')
        
        if not amount or not order_id:
            return error_response("Missing amount or order_id", "MISSING_DATA", 400)

        gateway, error = get_gateway_config('stripe')
        if not gateway:
            return error_response(error, "GATEWAY_ERROR", 404)
            
        secret_key = gateway.get_encrypted_key('secret_key') or gateway.config.get('secret_key')
        if not secret_key:
            return error_response("Stripe misconfigured", "CONFIG_ERROR", 500)
            
        stripe.api_key = secret_key
        
        order = Order.query.get(order_id)
        if not order:
            return error_response("Order not found", "NOT_FOUND", 404)
            
        intent = stripe.PaymentIntent.create(
            amount=int(float(amount) * 100),
            currency=currency.lower(),
            metadata={'order_id': order_id, 'order_number': order.order_number},
            automatic_payment_methods={'enabled': True}
        )
        
        return success_response({
            "client_secret": intent.client_secret,
            "id": intent.id
        })
        
    except stripe.error.StripeError as e:
        return error_response(str(e), "STRIPE_ERROR", 400)
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@payment_bp.route('/stripe/confirm', methods=['POST'])
@require_api_auth(optional=False)
def confirm_stripe_payment():
    """
    Confirm Stripe Payment and update Order.
    PROPOSE: Webhook is better, but this endpoint allows client-side confirmation trigger.
    """
    try:
        data = request.get_json()
        payment_intent_id = data.get('payment_intent_id')
        order_id = data.get('order_id')
        
        gateway, error = get_gateway_config('stripe')
        if not gateway: return error_response(error, "GATEWAY_ERROR", 404)
        
        stripe.api_key = gateway.get_encrypted_key('secret_key') or gateway.config.get('secret_key')
        
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        if intent.status == 'succeeded':
            order = Order.query.get(order_id)
            if order:
                order.status = 'processing'
                order.payment_transaction_id = intent.id
                order.payment_method = 'stripe'
                db.session.commit()
                return success_response({"status": "succeeded"})
        
        return error_response(f"Payment status: {intent.status}", "PAYMENT_FAILED", 400)
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

# PayPal implementation omitted for brevity but would follow similar pattern
# For now, we focus on standardized structure as requested. Be perfect.
