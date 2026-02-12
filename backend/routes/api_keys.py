from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import db
from models.api_key import APIKey
from utils.permissions import login_required
from utils.auth import get_current_user
from datetime import datetime, timedelta

api_keys = Blueprint('api_keys', __name__, url_prefix='/admin/api-keys')

@api_keys.route('/', methods=['GET'])
@api_keys.route('/list', methods=['GET'])
@login_required
def list():
    """List all API keys"""
    keys = APIKey.query.order_by(APIKey.created_at.desc()).all()
    return render_template('api_keys/list.html', api_keys=keys)

@api_keys.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create a new API key"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        expires_in_days = request.form.get('expires_in_days', '')
        
        # Validation
        if not name:
            flash('API key name is required', 'error')
            return render_template('api_keys/create.html', 
                                 form_data={
                                     'name': name,
                                     'description': description,
                                     'expires_in_days': expires_in_days
                                 })
        
        # Check if name already exists
        if APIKey.query.filter_by(name=name).first():
            flash('An API key with this name already exists', 'error')
            return render_template('api_keys/create.html',
                                 form_data={
                                     'name': name,
                                     'description': description,
                                     'expires_in_days': expires_in_days
                                 })
        
        # Generate API key and secret
        api_key = APIKey.generate_api_key()
        api_secret = APIKey.generate_api_secret()
        api_secret_hash = APIKey.hash_secret(api_secret)
        
        # Calculate expiration date if provided
        expires_at = None
        if expires_in_days and expires_in_days.isdigit():
            expires_at = datetime.utcnow() + timedelta(days=int(expires_in_days))
        
        # Get current user
        current_user = get_current_user()
        
        # Create API key record
        new_api_key = APIKey(
            name=name,
            api_key=api_key,
            api_secret_hash=api_secret_hash,
            api_secret_plain=api_secret,  # Store temporarily to show once
            description=description,
            expires_at=expires_at,
            created_by=current_user.id if current_user else None,
            is_active=True
        )
        
        db.session.add(new_api_key)
        db.session.commit()
        
        # Redirect to success page showing the keys
        return redirect(url_for('api_keys.success', id=new_api_key.id))
    
    return render_template('api_keys/create.html')

@api_keys.route('/success/<int:id>', methods=['GET'])
@login_required
def success(id):
    """Show API key and secret after creation (one-time view)"""
    api_key_obj = APIKey.query.get_or_404(id)
    
    # Get the plain secret before it's cleared
    api_secret = api_key_obj.api_secret_plain
    
    # Clear the plain secret from database after first view
    if api_key_obj.api_secret_plain:
        api_key_obj.api_secret_plain = None
        db.session.commit()
    
    return render_template('api_keys/success.html', api_key=api_key_obj, api_secret=api_secret)

@api_keys.route('/<int:id>/toggle', methods=['POST'])
@login_required
def toggle(id):
    """Toggle API key active status"""
    api_key = APIKey.query.get_or_404(id)
    api_key.is_active = not api_key.is_active
    db.session.commit()
    
    status = 'activated' if api_key.is_active else 'deactivated'
    flash(f'API key "{api_key.name}" has been {status}', 'success')
    return redirect(url_for('api_keys.list'))

@api_keys.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Delete an API key"""
    api_key = APIKey.query.get_or_404(id)
    name = api_key.name
    db.session.delete(api_key)
    db.session.commit()
    
    flash(f'API key "{name}" has been deleted', 'success')
    return redirect(url_for('api_keys.list'))
