from functools import wraps
from flask import request, g, jsonify, current_app, session
from models.api_key import APIKey
from datetime import datetime
from models import db

def require_api_auth(optional=False):
    """
    Decorator to require API Key authentication.
    
    Args:
        optional (bool): If True, allows request even if auth is missing (but g.api_key will be None).
                         If keys are provided but invalid, it still returns 401.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Allow Session-based auth (for Admin Panel)
            if 'user_id' in session:
                g.api_key = 'SESSION_USER'
                g.is_master = False
                # We could attach g.current_user here if we imported User model, but not strictly needed for just bypassing auth
                return f(*args, **kwargs)

            api_key = request.headers.get('X-API-Key')
            api_secret = request.headers.get('X-API-Secret')
            
            # Check for legacy/master hardcoded key from Config (emergency access)
            # This is useful for initial setup or internal tools not yet migrated
            master_key = current_app.config.get('API_KEY')
            master_secret = current_app.config.get('API_SECRET')
            
            if master_key and master_secret and api_key == master_key and api_secret == master_secret:
                g.api_key = 'MASTER'
                g.is_master = True
                return f(*args, **kwargs)

            if not api_key:
                if optional:
                    g.api_key = None
                    return f(*args, **kwargs)
                return jsonify({
                    'success': False,
                    'error': 'Missing authentication credentials',
                    'code': 'MISSING_CREDENTIALS'
                }), 401
            
            # Look up API key in database
            key_obj = APIKey.query.filter_by(api_key=api_key).first()
            
            if not key_obj:
                return jsonify({
                    'success': False,
                    'error': 'Invalid API Key',
                    'code': 'INVALID_KEY'
                }), 401
                
            if not key_obj.is_active:
                return jsonify({
                    'success': False,
                    'error': 'API Key is inactive',
                    'code': 'INACTIVE_KEY'
                }), 403
                
            if key_obj.is_expired():
                return jsonify({
                    'success': False,
                    'error': 'API Key has expired',
                    'code': 'EXPIRED_KEY'
                }), 403

            # Verify secret if provided (enforce strictly for write ops if needed, 
            # but for now we enforce if the header is present or if we want stricter security.
            # The prompt asked to start using "API Keys and API Secrets".
            # To be safe and "Perfect", we should check secret if it's stored.)
            
            # Note: Public clients might only have the Key. 
            # If the user insists on "Authenticated using these API Key and API Secrets",
            # we should check the secret.
            
            if not api_secret:
                 return jsonify({
                    'success': False,
                    'error': 'Missing API Secret',
                    'code': 'MISSING_SECRET'
                }), 401

            if not key_obj.verify_secret(api_secret):
                return jsonify({
                    'success': False,
                    'error': 'Invalid API Secret',
                    'code': 'INVALID_SECRET'
                }), 401

            # Update last used
            try:
                key_obj.last_used = datetime.utcnow()
                db.session.commit()
            except:
                pass # distinct updates tracking shouldn't block the request

            g.api_key = key_obj
            g.is_master = False
            return f(*args, **kwargs)
        return decorated_function
    return decorator
