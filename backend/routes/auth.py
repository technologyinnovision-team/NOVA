from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import db
from models.user import User, Role
from models.pos import POSSellerProfile
from utils.auth import hash_password, verify_password, login_user, logout_user, get_current_user
from utils.permissions import login_required

auth = Blueprint('auth', __name__, url_prefix='/admin/auth')

@auth.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'
        
        if not username or not password:
            flash('Please enter both username and password.', 'error')
            return render_template('auth/login.html')
        
        user = User.query.filter_by(username=username, is_active=True).first()
        
        if user and verify_password(user.password_hash, password):
            login_user(user)
            
            flash(f'Welcome back, {user.username}!', 'success')
            
            # Redirect based on user role
            if user.role.name == Role.POS_SELLER:
                # [FIX] Auto-create profile if missing
                if not user.pos_profile:
                     pos_profile = POSSellerProfile(
                        user_id=user.id,
                        business_name=user.username
                    )
                     db.session.add(pos_profile)
                     db.session.commit()
                     # Refresh user to get the relationship
                     db.session.refresh(user)

                # POS Seller goes to POS dashboard
                next_page = request.args.get('next') or url_for('pos_dashboard.dashboard')
            else:
                # Admin/Other users go to admin dashboard
                next_page = request.args.get('next') or url_for('dashboard.index')
            
            return redirect(next_page)
        else:
            flash('Invalid username or password.', 'error')
    
    # If already logged in, redirect to dashboard
    if 'user_id' in session:
        user = get_current_user()
        if user and user.pos_profile:
            return redirect(url_for('pos_dashboard.dashboard'))
        return redirect(url_for('dashboard.index'))
    
    return render_template('auth/login.html')

@auth.route('/logout')
@login_required
def logout():
    """Logout user"""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

@auth.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change password page"""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        user = User.query.get(session['user_id'])
        
        if not verify_password(user.password_hash, current_password):
            flash('Current password is incorrect.', 'error')
            return render_template('auth/change_password.html')
        
        if len(new_password) < 8:
            flash('New password must be at least 8 characters long.', 'error')
            return render_template('auth/change_password.html')
        
        if new_password != confirm_password:
            flash('New passwords do not match.', 'error')
            return render_template('auth/change_password.html')
        
        user.password_hash = hash_password(new_password)
        db.session.commit()
        
        flash('Password changed successfully.', 'success')
        return redirect(url_for('dashboard.index'))
    
    return render_template('auth/change_password.html')

