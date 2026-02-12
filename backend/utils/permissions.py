from functools import wraps
from flask import redirect, url_for, flash
from utils.auth import get_current_user

def require_permission(permission):
    """Decorator to require a specific permission"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                flash('Please login to access this page.', 'error')
                return redirect(url_for('auth.login'))
            
            if not user.check_permission(permission):
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('dashboard.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_role(*roles):
    """Decorator to require specific roles"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                flash('Please login to access this page.', 'error')
                return redirect(url_for('auth.login'))
            
            if not user.role or user.role.name not in roles:
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('dashboard.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from utils.auth import is_authenticated
        if not is_authenticated():
            flash('Please login to access this page.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            flash('Please login.', 'error')
            return redirect(url_for('auth.login')) # Note: API should probably return 401, but keeping consistent with app style
            
        # Check if user has 'all' permission or is Super Admin/Admin
        if user.role and (user.role.name in ['Super Admin', 'Admin'] or user.check_permission('all')):
            return f(*args, **kwargs)
            
        flash('Admin access required.', 'error')
        return redirect(url_for('dashboard.index'))
    return decorated_function

