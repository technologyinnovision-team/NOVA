from flask import Blueprint, request, session
from api.utils import success_response, error_response, validate_request_json
from utils.validators import validate_email
import random
import string
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__)

# In-memory OTP storage (use Redis in production)
otp_storage = {}

def generate_otp():
    """Generate 6-digit OTP"""
    return ''.join([str(random.randint(0, 9)) for _ in range(6)])

@auth_bp.route('/send-otp', methods=['POST'])
@validate_request_json(['email'])
def send_otp():
    """Send OTP to email/phone"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        phone = data.get('phone', '').strip()
        
        if not email and not phone:
            return error_response("Email or phone required", "MISSING_DATA", 400)
        
        if email and not validate_email(email):
            return error_response("Invalid email address", "INVALID_EMAIL", 400)
        
        # Generate OTP
        otp = generate_otp()
        identifier = email or phone
        expires_at = datetime.utcnow() + timedelta(minutes=10)
        
        # Store OTP
        otp_storage[identifier] = {
            'otp': otp,
            'expires_at': expires_at,
            'attempts': 0
        }
        
        # In production, send OTP via email/SMS service
        # For now, we'll just return success (in dev, you might want to log the OTP)
        print(f"OTP for {identifier}: {otp}")  # Remove in production
        
        return success_response({
            "sent": True,
            "identifier": identifier,
            "expires_in": 600  # 10 minutes in seconds
        }, "OTP sent successfully")
        
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@auth_bp.route('/verify-otp', methods=['POST'])
@validate_request_json(['email', 'otp'])
def verify_otp():
    """Verify OTP"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        phone = data.get('phone', '').strip()
        otp = data.get('otp', '').strip()
        
        identifier = email or phone
        if not identifier:
            return error_response("Email or phone required", "MISSING_DATA", 400)
        
        # Check OTP
        stored = otp_storage.get(identifier)
        if not stored:
            return error_response("OTP not found or expired", "OTP_NOT_FOUND", 400)
        
        # Check expiration
        if datetime.utcnow() > stored['expires_at']:
            del otp_storage[identifier]
            return error_response("OTP expired", "OTP_EXPIRED", 400)
        
        # Check attempts
        if stored['attempts'] >= 5:
            del otp_storage[identifier]
            return error_response("Too many attempts", "TOO_MANY_ATTEMPTS", 400)
        
        # Verify OTP
        stored['attempts'] += 1
        if stored['otp'] != otp:
            return error_response("Invalid OTP", "INVALID_OTP", 400)
        
        # OTP verified - create session token
        session_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
        session[f'auth_token_{identifier}'] = {
            'token': session_token,
            'verified_at': datetime.utcnow().isoformat(),
            'identifier': identifier
        }
        
        # Clean up OTP
        del otp_storage[identifier]
        
        return success_response({
            "verified": True,
            "token": session_token,
            "identifier": identifier
        }, "OTP verified successfully")
        
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@auth_bp.route('/guest-checkout', methods=['POST'])
@validate_request_json(['email', 'otp'])
def guest_checkout():
    """Guest checkout with OTP verification"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        otp = data.get('otp', '').strip()
        
        if not validate_email(email):
            return error_response("Invalid email address", "INVALID_EMAIL", 400)
        
        # Verify OTP first
        stored = otp_storage.get(email)
        if not stored:
            return error_response("OTP not found. Please request OTP first.", "OTP_NOT_FOUND", 400)
        
        if datetime.utcnow() > stored['expires_at']:
            del otp_storage[email]
            return error_response("OTP expired", "OTP_EXPIRED", 400)
        
        if stored['otp'] != otp:
            return error_response("Invalid OTP", "INVALID_OTP", 400)
        
        # OTP verified - allow guest checkout
        session_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
        session[f'guest_checkout_{email}'] = {
            'token': session_token,
            'email': email,
            'verified_at': datetime.utcnow().isoformat()
        }
        
        del otp_storage[email]
        
        return success_response({
            "verified": True,
            "token": session_token,
            "email": email
        }, "Guest checkout verified")
        
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

