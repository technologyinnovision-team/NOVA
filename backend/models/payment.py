from datetime import datetime
from . import db
from cryptography.fernet import Fernet
from flask import current_app
import base64
import os

class PaymentGateway(db.Model):
    __tablename__ = 'payment_gateways'
    
    id = db.Column(db.Integer, primary_key=True)
    gateway_name = db.Column(db.String(50), unique=True, nullable=False)  # stripe, paypal
    enabled = db.Column(db.Boolean, default=False, nullable=False)
    config = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<PaymentGateway {self.gateway_name}>'
    
    def set_encrypted_key(self, key_name, value):
        """Encrypt and store sensitive keys"""
        if not value:
            return
        try:
            secret_key = current_app.config.get('SECRET_KEY', 'dev-secret-key-change-in-production')
            # Use first 32 bytes of secret key, pad if needed
            key_bytes = (secret_key[:32] + '0' * 32)[:32].encode()
            key = base64.urlsafe_b64encode(key_bytes)
            fernet = Fernet(key)
            encrypted = fernet.encrypt(value.encode())
            
            if not self.config:
                self.config = {}
            self.config[f'{key_name}_encrypted'] = encrypted.decode()
        except Exception as e:
            print(f"Error encrypting key: {e}")
    
    def get_encrypted_key(self, key_name):
        """Decrypt and retrieve sensitive keys"""
        try:
            if not self.config:
                print(f"get_encrypted_key: No config found for {key_name}")
                return None
            
            encrypted_key_name = f'{key_name}_encrypted'
            direct_key_name = key_name
            
            # Method 1: Try to decrypt encrypted key first
            if encrypted_key_name in self.config:
                try:
                    encrypted_value = self.config[encrypted_key_name]
                    if not encrypted_value:
                        print(f"get_encrypted_key: {encrypted_key_name} exists but is empty")
                    else:
                        secret_key = current_app.config.get('SECRET_KEY', 'dev-secret-key-change-in-production')
                        key_bytes = (secret_key[:32] + '0' * 32)[:32].encode()
                        key = base64.urlsafe_b64encode(key_bytes)
                        fernet = Fernet(key)
                        
                        decrypted = fernet.decrypt(encrypted_value.encode())
                        decrypted_str = decrypted.decode()
                        print(f"get_encrypted_key: Successfully decrypted {key_name}")
                        return decrypted_str
                except Exception as decrypt_error:
                    print(f"get_encrypted_key: Error decrypting {key_name}: {decrypt_error}")
                    import traceback
                    traceback.print_exc()
                    # Fall through to try direct config access
            
            # Method 2: Fallback to direct config access
            if direct_key_name in self.config:
                direct_key = self.config[direct_key_name]
                if direct_key:
                    # For Stripe keys, validate format
                    if key_name == 'secret_key':
                        if isinstance(direct_key, str) and direct_key.startswith(('sk_test_', 'sk_live_')):
                            print(f"get_encrypted_key: Using direct {key_name} from config")
                            return direct_key
                        else:
                            print(f"get_encrypted_key: Direct {key_name} found but invalid format (starts with: {direct_key[:10] if len(direct_key) > 10 else direct_key})")
                    else:
                        # For other keys, just return if it's a string
                        if isinstance(direct_key, str):
                            print(f"get_encrypted_key: Using direct {key_name} from config")
                            return direct_key
            
            print(f"get_encrypted_key: No valid key found for {key_name}")
            return None
        except Exception as e:
            print(f"get_encrypted_key: Exception getting {key_name}: {e}")
            import traceback
            traceback.print_exc()
            return None

