from werkzeug.security import generate_password_hash, check_password_hash
from flask import session
from models.user import User
from models import db
from datetime import datetime

def hash_password(password):
    """Generate password hash"""
    return generate_password_hash(password)

def verify_password(password_hash, password):
    """Verify password against hash"""
    return check_password_hash(password_hash, password)

def login_user(user):
    """Login user and set session"""
    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role.name if user.role else None
    session.permanent = True
    
    # Update last login
    user.last_login = datetime.utcnow()
    db.session.commit()

def logout_user():
    """Logout user and clear session"""
    session.clear()

def get_current_user():
    """Get current logged in user"""
    if 'user_id' not in session:
        return None
    return User.query.get(session['user_id'])

def is_authenticated():
    """Check if user is authenticated"""
    return 'user_id' in session

def require_login():
    """Decorator helper - check if user is logged in"""
    return is_authenticated()

