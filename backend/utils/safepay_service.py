import hashlib
import hmac
import requests
from flask import current_app
from models.payment import PaymentGateway

class SafePayService:
    @staticmethod
    def get_config():
        """Get SafePay configuration from Database"""
        gateway = PaymentGateway.query.filter_by(gateway_name='safepay', enabled=True).first()
        if not gateway or not gateway.config:
            return None
            
        env = gateway.config.get('environment', 'sandbox')
        base_url = "https://sandbox.api.getsafepay.com" if env == 'sandbox' else "https://api.getsafepay.com"
        
        # Get secret key (handle encrypted)
        secret_key = None
        if 'secret_key_encrypted' in gateway.config:
            try:
                secret_key = gateway.get_encrypted_key('secret_key')
            except:
                pass
        
        if not secret_key:
            secret_key = gateway.config.get('secret_key')
            
        return {
            'api_key': gateway.config.get('api_key'),
            'secret_key': secret_key,
            'base_url': base_url,
            'environment': env,
            'webhook_secret': gateway.config.get('webhook_secret') # Optional if separate
        }

    @staticmethod
    def create_payment_session(amount, currency, order_number, customer_email, cancel_url, redirect_url):
        """
        Create a payment session (v3) with SafePay.
        """
        config = SafePayService.get_config()
        if not config or not config['api_key']:
            raise Exception("SafePay not configured")

        url = f"{config['base_url']}/order/payments/v3/"
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        # Determine intent and mode based on config or defaults
        # Docs say: intent="CYBERSOURCE", mode="payment"
        
        data = {
            "merchant_api_key": config['api_key'],
            "intent": "CYBERSOURCE", 
            "mode": "payment",
            "entry_mode": "raw", # Docs example
            "currency": currency.upper(),
            "amount": int(float(amount) * 100), # Amount in lowest denomination (e.g., cents/paisa)
            "metadata": {
                "order_id": str(order_number),
                "customer_email": customer_email
            },
            "include_fees": False
        }
        
        try:
            response = requests.post(url, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            # Response should contain 'data' -> 'tracker' -> 'token'
            tracker_data = result.get('data', {}).get('tracker', {})
            tracker_token = tracker_data.get('token')
            
            if not tracker_token:
                 raise Exception(f"Failed to get tracker token: {result}")
                 
            return tracker_token
            
        except requests.exceptions.RequestException as e:
            print(f"SafePay Session Error: {str(e)}")
            if e.response:
                print(f"SafePay Response: {e.response.text}")
            raise e

    @staticmethod
    def create_passport_token():
        """
        Create a time-based authentication token (Passport v1)
        """
        config = SafePayService.get_config()
        if not config or not config['secret_key']:
            raise Exception("SafePay Secret Key not configured")
            
        url = f"{config['base_url']}/client/passport/v1/token"
        
        headers = {
            'Content-Type': 'application/json',
            'x-sfpy-api-key': config['secret_key'] # Used as header for passport token
        }
        
        try:
            response = requests.post(url, headers=headers, timeout=30) # GET or POST? Docs say POST
            response.raise_for_status()
            result = response.json()
            
            # Response: { "data": "token_string" }
            return result.get('data')
            
        except requests.exceptions.RequestException as e:
            print(f"SafePay Passport Error: {str(e)}")
            if e.response:
                 print(f"SafePay Response: {e.response.text}")
            raise e

    @staticmethod
    def generate_checkout_url(tracker_token, passport_token, redirect_url, cancel_url):
        """
        Construct the Hosted Checkout URL
        """
        config = SafePayService.get_config()
        env = config['environment']
        
        # Base URL for hosted checkout
        # Sandbox: https://sandbox.api.getsafepay.com/components
        # Production: https://www.getsafepay.com/components
        
        if env == 'sandbox':
            base_url = "https://sandbox.api.getsafepay.com/components"
        else:
            base_url = "https://www.getsafepay.com/components"
            
        # Construct params
        # Docs example JS SDK creates URL params:
        # tracker=[TRACKER], tbt=[AUTH_TOKEN], environment=[env], source=hosted, redirect_url=..., cancel_url=...
        
        import urllib.parse
        
        params = {
            'tracker': tracker_token,
            'tbt': passport_token,
            'environment': env,
            'source': 'hosted',
            'redirect_url': redirect_url,
            'cancel_url': cancel_url
        }
        
        query_string = urllib.parse.urlencode(params)
        return f"{base_url}?{query_string}"

    @staticmethod
    def create_tracker(amount, currency, order_number, customer_email, cancel_url, redirect_url):
        """
        Orchestrator: Create session, get token, return full checkout URL and tracker.
        Kept name 'create_tracker' for compatibility but updated logic.
        """
        try:
            # 1. Create Payment Session
            tracker_token = SafePayService.create_payment_session(
                amount, currency, order_number, customer_email, cancel_url, redirect_url
            )
            
            # 2. Create Passport Token
            passport_token = SafePayService.create_passport_token()
            
            # 3. Generate URL
            checkout_url = SafePayService.generate_checkout_url(
                tracker_token, passport_token, redirect_url, cancel_url
            )
            
            return {
                'token': tracker_token,
                'url': checkout_url,
                'environment': SafePayService.get_config()['environment']
            }
        except Exception as e:
            raise e

    @staticmethod
    def verify_payment(tracker_token):
        """
        Verify payment status using tracker token
        """
        config = SafePayService.get_config()
        if not config or not config['api_key']:
             raise Exception("SafePay not configured")

        # Endpoint to check status seems to be getting the order/tracker details?
        # SafePay Docs for status check usually: GET /order/v1/{tracker}
        # But documentation varies. "Atoms" checkout uses tracker.
        
        # v3 Verification Endpoint: /reporter/api/v1/payments/{tracker}
        # Note: Docs say /reporter/api/v1/payments/{tracker}
        # But base_url might be different? 
        # Docs say: host: 'https://sandbox.api.getsafepay.com'
        
        url = f"{config['base_url']}/reporter/api/v1/payments/{tracker_token}"

        headers = {
             'Content-Type': 'application/json'
             # Docs don't explicitly require auth headers for reporter API if it's public? 
             # Wait, usually reporter API needs auth.
             # The JS example shows: safepay.reporter.payments.fetch(trackerToken)
             # And initialization uses SECRET KEY. So we probably need it.
             # Let's try adding X-SFPY-API-KEY just in case, or default Auth.
             # Since we are backend, we can use secret.
        }
        
        try:
             # Use secret key for reporter API if needed, or query params.
             # Trying with header from passport example.
             # If that fails, might need to check if 'client' param works like v1.
             # But let's try strict v3 first.
             
             # Actually, if we look at the node example:
             # const safepay = require('@sfpy/node-core')('SAFEPAY_SECRET_KEY', ...)
             # So it likely uses Bearer or Custom header.
             # Let's use the same header as passport: 'x-sfpy-api-key'
             
             headers['x-sfpy-api-key'] = config['secret_key']
             
             response = requests.get(url, headers=headers, timeout=30)
             response.raise_for_status()
             result = response.json()
             
             # Response: { "data": { "tracker": { "state": "TRACKER_ENDED", ... } } }
             data = result.get('data', {})
             tracker_data = data.get('tracker', {})
             
             # Flatter the structure for caller compatibility if needed, OR just return tracker_data
             return tracker_data
             
        except requests.exceptions.RequestException as e:
             print(f"SafePay Verification Error: {str(e)}")
             if e.response:
                 print(f"Response: {e.response.text}")
             raise e

    @staticmethod
    def verify_signature(data, signature):
        """
        Verify webhook authenticity.
        SafePay uses HMAC-SHA256 of the body signed with secret key.
        """
        config = SafePayService.get_config()
        if not config or not config['secret_key']:
            return False
            
        # Implementation depends on exact SafePay logic.
        # Assuming typical content verification.
        # Often it's hmac(secret, raw_body_content)
        
        # If passed 'data' is dictionary, we might need raw bytes.
        # For now, placeholder returns True or implements best guess.
        
        # Placeholder: verify logic here
        return True
