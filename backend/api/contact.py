from flask import Blueprint, request
from api.utils import success_response, error_response, validate_request_json
from utils.validators import validate_email

contact_bp = Blueprint('contact', __name__)

@contact_bp.route('/contact', methods=['POST'])
@validate_request_json(['name', 'email', 'message'])
def submit_contact():
    """Submit contact form"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        message = data.get('message', '').strip()
        
        # Validate email
        if not validate_email(email):
            return error_response("Invalid email address", "INVALID_EMAIL", 400)
        
        # In production, you would:
        # 1. Send email notification
        # 2. Store in database
        # 3. Send auto-reply to customer
        
        # For now, just return success
        return success_response({
            "submitted": True,
            "name": name,
            "email": email
        }, "Contact form submitted successfully")
        
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

