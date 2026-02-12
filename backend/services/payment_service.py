import stripe
import paypalrestsdk
import os
import requests
from flask import current_app
from models.payment import PaymentGateway

class PaymentService:
    @staticmethod
    def init_app(app):
        """Initialize payment gateways from database configuration"""
        try:
            # Check if we're in application context
            with app.app_context():
                # Get Stripe configuration from database
                stripe_gateway = PaymentGateway.query.filter_by(gateway_name='stripe', enabled=True).first()
                if stripe_gateway:
                    secret_key = stripe_gateway.get_encrypted_key('secret_key')
                    if secret_key:
                        stripe.api_key = secret_key
                    else:
                        # Fallback to .env configuration
                        stripe.api_key = app.config.get('STRIPE_SECRET_KEY')
                else:
                    # Fallback to .env configuration
                    stripe.api_key = app.config.get('STRIPE_SECRET_KEY')
                
                # Get PayPal configuration from database
                paypal_gateway = PaymentGateway.query.filter_by(gateway_name='paypal', enabled=True).first()
                if paypal_gateway:
                    client_id = paypal_gateway.config.get('client_id')
                    client_secret = paypal_gateway.get_encrypted_key('secret')
                    mode = paypal_gateway.config.get('mode', 'sandbox')
                    
                    if client_id and client_secret:
                        paypalrestsdk.configure({
                            "mode": mode,
                            "client_id": client_id,
                            "client_secret": client_secret
                        })
                    else:
                        # Fallback to .env configuration
                        paypalrestsdk.configure({
                            "mode": app.config.get('PAYPAL_MODE', 'sandbox'),
                            "client_id": app.config.get('PAYPAL_CLIENT_ID'),
                            "client_secret": app.config.get('PAYPAL_CLIENT_SECRET')
                        })
                else:
                    # Fallback to .env configuration
                    paypalrestsdk.configure({
                        "mode": app.config.get('PAYPAL_MODE', 'sandbox'),
                        "client_id": app.config.get('PAYPAL_CLIENT_ID'),
                        "client_secret": app.config.get('PAYPAL_CLIENT_SECRET')
                    })
        except Exception as e:
            print(f"Error initializing payment gateways: {e}")
            # Fallback to .env configuration
            stripe.api_key = app.config.get('STRIPE_SECRET_KEY')
            paypalrestsdk.configure({
                "mode": app.config.get('PAYPAL_MODE', 'sandbox'),
                "client_id": app.config.get('PAYPAL_CLIENT_ID'),
                "client_secret": app.config.get('PAYPAL_CLIENT_SECRET')
            })

    @staticmethod
    def get_stripe_config():
        """Get Stripe configuration from database or fallback to env"""
        try:
            gateway = PaymentGateway.query.filter_by(gateway_name='stripe', enabled=True).first()
            if gateway:
                secret_key = gateway.get_encrypted_key('secret_key')
                publishable_key = gateway.config.get('publishable_key')
                return {
                    'secret_key': secret_key,
                    'publishable_key': publishable_key,
                    'enabled': True
                }
        except:
            pass
        
        # Fallback to env
        return {
            'secret_key': current_app.config.get('STRIPE_SECRET_KEY'),
            'publishable_key': current_app.config.get('STRIPE_PUBLIC_KEY'),
            'enabled': bool(current_app.config.get('STRIPE_SECRET_KEY'))
        }

    @staticmethod
    def get_paypal_config():
        """Get PayPal configuration from database or fallback to env"""
        try:
            gateway = PaymentGateway.query.filter_by(gateway_name='paypal', enabled=True).first()
            if gateway:
                client_id = gateway.config.get('client_id')
                client_secret = gateway.get_encrypted_key('secret')
                mode = gateway.config.get('mode', 'sandbox')
                return {
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'mode': mode,
                    'enabled': True
                }
        except:
            pass
        
        # Fallback to env
        return {
            'client_id': current_app.config.get('PAYPAL_CLIENT_ID'),
            'client_secret': current_app.config.get('PAYPAL_CLIENT_SECRET'),
            'mode': current_app.config.get('PAYPAL_MODE', 'sandbox'),
            'enabled': bool(current_app.config.get('PAYPAL_CLIENT_ID'))
        }

    @staticmethod
    def create_stripe_checkout_session(amount, currency='usd', success_url=None, cancel_url=None, metadata=None):
        """
        Create a Stripe Checkout Session (Hosted Payment Page)
        This is the recommended approach for accepting payments with Stripe.
        """
        try:
            config = PaymentService.get_stripe_config()
            if not config['enabled'] or not config['secret_key']:
                return {'success': False, 'error': 'Stripe is not configured or enabled'}
            
            stripe.api_key = config['secret_key']
            
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': currency,
                        'unit_amount': int(amount * 100),  # Convert to cents
                        'product_data': {
                            'name': metadata.get('description', 'Wallet Deposit'),
                        },
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=success_url,
                cancel_url=cancel_url,
                metadata=metadata or {}
            )
            
            return {
                'success': True,
                'session_id': session.id,
                'checkout_url': session.url
            }
        except stripe.error.StripeError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def create_stripe_payment_intent(amount, currency='usd', metadata=None):
        """
        Create a Stripe Payment Intent (for custom payment flows)
        Note: Checkout Sessions are preferred for most use cases.
        """
        try:
            config = PaymentService.get_stripe_config()
            if not config['enabled'] or not config['secret_key']:
                return {'success': False, 'error': 'Stripe is not configured or enabled'}
            
            stripe.api_key = config['secret_key']
            
            intent = stripe.PaymentIntent.create(
                amount=int(amount * 100),  # Convert to cents
                currency=currency,
                metadata=metadata or {},
                automatic_payment_methods={'enabled': True}
            )
            return {'success': True, 'client_secret': intent.client_secret, 'id': intent.id}
        except stripe.error.StripeError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def retrieve_stripe_session(session_id):
        """Retrieve a Stripe Checkout Session"""
        try:
            config = PaymentService.get_stripe_config()
            stripe.api_key = config['secret_key']
            session = stripe.checkout.Session.retrieve(session_id)
            return {'success': True, 'session': session}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def verify_stripe_webhook(payload, sig_header, webhook_secret):
        """Verify Stripe webhook signature"""
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
            return {'success': True, 'event': event}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def create_paypal_order(amount, currency='USD', return_url=None, cancel_url=None, description="Wallet Deposit"):
        """
        Create a PayPal Order using Orders API v2 (Modern approach)
        This replaces the deprecated Payments API
        """
        try:
            config = PaymentService.get_paypal_config()
            if not config['enabled'] or not config['client_id'] or not config['client_secret']:
                return {'success': False, 'error': 'PayPal is not configured or enabled'}
            
            # Get access token
            auth_response = requests.post(
                f"https://api-m.{'sandbox.' if config['mode'] == 'sandbox' else ''}paypal.com/v1/oauth2/token",
                headers={'Accept': 'application/json', 'Accept-Language': 'en_US'},
                auth=(config['client_id'], config['client_secret']),
                data={'grant_type': 'client_credentials'}
            )
            
            if auth_response.status_code != 200:
                return {'success': False, 'error': 'Failed to authenticate with PayPal'}
            
            access_token = auth_response.json()['access_token']
            
            # Create order
            order_data = {
                "intent": "CAPTURE",
                "purchase_units": [{
                    "amount": {
                        "currency_code": currency,
                        "value": f"{amount:.2f}"
                    },
                    "description": description
                }],
                "application_context": {
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                    "brand_name": "BaileBelle",
                    "user_action": "PAY_NOW"
                }
            }
            
            order_response = requests.post(
                f"https://api-m.{'sandbox.' if config['mode'] == 'sandbox' else ''}paypal.com/v2/checkout/orders",
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {access_token}'
                },
                json=order_data
            )
            
            if order_response.status_code != 201:
                return {'success': False, 'error': f'Failed to create PayPal order: {order_response.text}'}
            
            order = order_response.json()
            
            # Get approval URL
            approval_url = None
            for link in order.get('links', []):
                if link['rel'] == 'approve':
                    approval_url = link['href']
                    break
            
            if not approval_url:
                return {'success': False, 'error': 'Approval URL not found in PayPal response'}
            
            return {
                'success': True,
                'order_id': order['id'],
                'approval_url': approval_url
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def capture_paypal_order(order_id):
        """
        Capture a PayPal Order after user approval
        """
        try:
            config = PaymentService.get_paypal_config()
            if not config['enabled']:
                return {'success': False, 'error': 'PayPal is not enabled'}
            
            # Get access token
            auth_response = requests.post(
                f"https://api-m.{'sandbox.' if config['mode'] == 'sandbox' else ''}paypal.com/v1/oauth2/token",
                headers={'Accept': 'application/json', 'Accept-Language': 'en_US'},
                auth=(config['client_id'], config['client_secret']),
                data={'grant_type': 'client_credentials'}
            )
            
            if auth_response.status_code != 200:
                return {'success': False, 'error': 'Failed to authenticate with PayPal'}
            
            access_token = auth_response.json()['access_token']
            
            # Capture order
            capture_response = requests.post(
                f"https://api-m.{'sandbox.' if config['mode'] == 'sandbox' else ''}paypal.com/v2/checkout/orders/{order_id}/capture",
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {access_token}'
                }
            )
            
            if capture_response.status_code not in [200, 201]:
                return {'success': False, 'error': f'Failed to capture PayPal order: {capture_response.text}'}
            
            order = capture_response.json()
            
            # Extract amount from captured order
            amount = None
            if order.get('purchase_units') and len(order['purchase_units']) > 0:
                amount = float(order['purchase_units'][0]['payments']['captures'][0]['amount']['value'])
            
            return {
                'success': True,
                'order': order,
                'amount': amount,
                'status': order.get('status')
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def create_paypal_payout(recipient_email, amount, currency='USD', note="Payout from BaileBelle"):
        """
        Uses PayPal Payouts API to send money to a user.
        Note: This requires Payouts to be enabled on the PayPal account.
        """
        payout_item = {
            "recipient_type": "EMAIL",
            "amount": {
                "value": f"{amount:.2f}",
                "currency": currency
            },
            "receiver": recipient_email,
            "note": note,
            "sender_item_id": f"payout_{os.urandom(4).hex()}"
        }

        payout_batch = paypalrestsdk.Payout({
            "sender_batch_header": {
                "sender_batch_id": f"batch_{os.urandom(8).hex()}",
                "email_subject": "You have a payout!"
            },
            "items": [payout_item]
        })

        if payout_batch.create(sync_mode=True):
            return {'success': True, 'batch_id': payout_batch.batch_header.payout_batch_id}
        else:
            return {'success': False, 'error': payout_batch.error}

    # Legacy methods kept for backward compatibility
    @staticmethod
    def create_paypal_payment(amount, return_url, cancel_url, currency='USD', description="Wallet Deposit"):
        """DEPRECATED: Use create_paypal_order instead. This uses the old Payments API."""
        payment = paypalrestsdk.Payment({
            "intent": "sale",
            "payer": {
                "payment_method": "paypal"
            },
            "redirect_urls": {
                "return_url": return_url,
                "cancel_url": cancel_url
            },
            "transactions": [{
                "item_list": {
                    "items": [{
                        "name": description,
                        "sku": "deposit",
                        "price": f"{amount:.2f}",
                        "currency": currency,
                        "quantity": 1
                    }]
                },
                "amount": {
                    "total": f"{amount:.2f}",
                    "currency": currency
                },
                "description": description
            }]
        })

        if payment.create():
            # Extract approval URL
            for link in payment.links:
                if link.rel == "approval_url":
                    return {'success': True, 'approval_url': link.href, 'payment_id': payment.id}
            return {'success': False, 'error': 'Approval URL not found'}
        else:
            return {'success': False, 'error': payment.error}

    @staticmethod
    def execute_paypal_payment(payment_id, payer_id):
        """DEPRECATED: Use capture_paypal_order instead. This uses the old Payments API."""
        payment = paypalrestsdk.Payment.find(payment_id)

        if payment.execute({"payer_id": payer_id}):
            return {'success': True, 'payment': payment}
        else:
            return {'success': False, 'error': payment.error}
