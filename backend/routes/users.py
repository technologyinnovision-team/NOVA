from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash
from models import db, User, Role
from models.pos import POSSellerProfile
from utils.permissions import admin_required, login_required
from utils.auth import get_current_user

users_bp = Blueprint('users', __name__, url_prefix='/admin/users')

@users_bp.route('/')
@login_required
@admin_required
def list_users():
    """List all users except customers (unless specified)"""
    # Simply list all users for now, can filter in template or query if needed
    users = User.query.options(db.joinedload(User.role)).all()
    return render_template('users/list.html', users=users)

@users_bp.route('/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    roles = Role.query.all()
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role_id = request.form.get('role_id')
        is_active = True if request.form.get('is_active') else False
        
        # Validation
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return render_template('users/form.html', roles=roles)
        if User.query.filter_by(email=email).first():
            flash('Email already exists.', 'error')
            return render_template('users/form.html', roles=roles)
            
        hashed_password = generate_password_hash(password)
        
        new_user = User(
            username=username,
            email=email,
            password_hash=hashed_password,
            role_id=role_id,
            is_active=is_active
        )
        
        try:
            db.session.add(new_user)
            db.session.flush() # Flush to get the ID

            # Check if role is POS Seller Create Profile
            role = Role.query.get(role_id)
            if role and role.name == Role.POS_SELLER:
                if not new_user.pos_profile:
                    pos_profile = POSSellerProfile(
                        user_id=new_user.id,
                        business_name=new_user.username # Default to username
                    )
                    db.session.add(pos_profile)

            db.session.commit()
            flash('User created successfully.', 'success')
            return redirect(url_for('users.list_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating user: {str(e)}', 'error')
            
    return render_template('users/form.html', roles=roles)

@users_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(id):
    user = User.query.get_or_404(id)
    roles = Role.query.all()
    
    if request.method == 'POST':
        user.username = request.form.get('username')
        user.email = request.form.get('email')
        user.role_id = request.form.get('role_id')
        user.is_active = True if request.form.get('is_active') else False
        
        if request.form.get('password'):
            user.password_hash = generate_password_hash(request.form.get('password'))
            
        try:
            db.session.commit()
            
            # Check if role is POS Seller and Profile Missing
            if user.role.name == Role.POS_SELLER:
                if not user.pos_profile:
                    pos_profile = POSSellerProfile(
                        user_id=user.id,
                        business_name=user.username
                    )
                    db.session.add(pos_profile)
                    db.session.commit()

            flash('User updated successfully.', 'success')
            return redirect(url_for('users.list_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating user: {str(e)}', 'error')
            
    return render_template('users/form.html', user=user, roles=roles)

@users_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(id):
    current_user = get_current_user()
    if id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('users.list_users'))
        
    user = User.query.get_or_404(id)
    try:
        db.session.delete(user)
        db.session.commit()
        flash('User deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {str(e)}', 'error')
        
    return redirect(url_for('users.list_users'))
