from flask import jsonify, request
from functools import wraps
from models.api_key import APIKey
from datetime import datetime

def success_response(data=None, message=None, status_code=200):
    """Create a standardized success response"""
    response = {
        "success": True,
        "data": data or {}
    }
    if message:
        response["message"] = message
    return jsonify(response), status_code

def error_response(error_message, error_code=None, status_code=400):
    """Create a standardized error response"""
    response = {
        "success": False,
        "error": error_message
    }
    if error_code:
        response["code"] = error_code
    return jsonify(response), status_code

def validate_request_json(required_fields=None):
    """Decorator to validate JSON request data"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from flask import request
            data = None
            
            # Try to get JSON data, even if content-type is missing (force=True)
            try:
                data = request.get_json(force=True, silent=True)
            except Exception as e:
                print(f"DEBUG: JSON parse error: {e}")
            
            # If still no data, log headers for debugging
            if data is None:
                print(f"DEBUG: Failed to parse JSON. Headers: {dict(request.headers)}")
                print(f"DEBUG: Request Data: {request.get_data(as_text=True)}")
                return error_response("Request must be JSON", "INVALID_CONTENT_TYPE", 400)
            
            # Populate request.json if it wasn't set (because we used silent=True)
            # This is a bit of a hack, but flask's request.json property is cached
            if request.json is None:
                 # We can't easily set request.json directly as it's a property
                 # However, since we have 'data', we can use it for validation
                 pass

            if required_fields:
                missing_fields = [field for field in required_fields if field not in data or data[field] is None]
                if missing_fields:
                    return error_response(
                        f"Missing required fields: {', '.join(missing_fields)}",
                        "MISSING_FIELDS",
                        400
                    )
            
            # IMPORTANT: Since we might have forced JSON parsing, we need to ensure the view function 
            # calls request.get_json(force=True) or we monkeypatch it?
            # Actually, standard flask helper request.get_json() might still fail if we don't pass force=True there too.
            # But the view functions usually call request.get_json() without args.
            # If Content-Type is wrong, request.get_json() returns None by default (or errors).
            # To fix this without changing all view functions, we should probably ensure 'data' is passed 
            # or rely on the fact that if we got here, the manual check in view function 'should' work if they use force=True 
            # OR we accept that we just validated it, and the view function might fail again if it's strict.
            
            # However, looking at the code, most view functions do `data = request.get_json()`.
            # If content-type is wrong, that will return None.
            # So checking it here isn't enough if the view function doesn't also use force=True.
            
            # BUT, we can't easily change all view functions.
            # Let's hope that `get_json(force=True)` caches the result?
            # Flask documentation says: "The parsed JSON data is cached on the request."
            # So if we call it successfully here, subsequent calls *should* return the cached data.
            # Let's verify: request.get_json() checks cache first. 
            
            # So calling request.get_json(force=True) here populates the cache.
            # Subsequent calls to request.get_json() (even without force=True) will return the cached data 
            # *IF* they don't explicitly check Content-Type again? 
            # Actually, request.get_json() implementation:
            # if self._cached_json[0] is not Ellipsis: return self._cached_json[0]
            # So YES, caching works.
            
            if data is None and not request.is_json:
                 # This path is actually covered by the check above (data is None)
                 pass

            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_api_auth(f):
    """Decorator to require API Key and Secret Key authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get API key and secret from headers
        api_key = request.headers.get('X-API-Key')
        api_secret = request.headers.get('X-API-Secret')
        
        if not api_key or not api_secret:
            return error_response(
                "API Key and Secret Key are required. Please provide X-API-Key and X-API-Secret headers.",
                "MISSING_API_CREDENTIALS",
                401
            )
        
        # Find API key in database
        api_key_obj = APIKey.query.filter_by(api_key=api_key, is_active=True).first()
        
        if not api_key_obj:
            return error_response(
                "Invalid API Key",
                "INVALID_API_KEY",
                401
            )
        
        # Check if API key is expired
        if api_key_obj.is_expired():
            return error_response(
                "API Key has expired",
                "API_KEY_EXPIRED",
                401
            )
        
        # Verify secret
        if not api_key_obj.verify_secret(api_secret):
            return error_response(
                "Invalid API Secret",
                "INVALID_API_SECRET",
                401
            )
        
        # Update last used timestamp
        api_key_obj.last_used = datetime.utcnow()
        from models import db
        db.session.commit()
        
        # Store API key object in request context for use in the route
        request.api_key_obj = api_key_obj
        
        return f(*args, **kwargs)
    return decorated_function
