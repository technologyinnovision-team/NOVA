from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db
from models.stitching import StitchingService
from utils.permissions import login_required

stitching = Blueprint('stitching', __name__, url_prefix='/admin/stitching')

@stitching.route('/', methods=['GET'])
@login_required
def list_services():
    services = StitchingService.query.order_by(StitchingService.name).all()
    return render_template('settings/stitching_services.html', services=services)

@stitching.route('/create', methods=['POST'])
@login_required
def create_service():
    name = request.form.get('name')
    price = request.form.get('price')
    is_active = request.form.get('is_active') == 'on'
    
    if not name or not price:
        flash('Name and Price are required.', 'error')
        return redirect(url_for('stitching.list_services'))
        
    try:
        service = StitchingService(name=name, price=price, is_active=is_active)
        db.session.add(service)
        db.session.commit()
        flash('Stitching Service created successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating service: {str(e)}', 'error')
        
    return redirect(url_for('stitching.list_services'))

@stitching.route('/edit/<int:id>', methods=['POST'])
@login_required
def edit_service(id):
    service = StitchingService.query.get_or_404(id)
    menu_active_tab = "settings" # Helper for sidebar if needed
    
    name = request.form.get('name')
    price = request.form.get('price')
    is_active = request.form.get('is_active') == 'on'
    
    if not name or not price:
        flash('Name and Price are required.', 'error')
        return redirect(url_for('stitching.list_services'))
        
    try:
        service.name = name
        service.price = price
        service.is_active = is_active
        db.session.commit()
        flash('Stitching Service updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating service: {str(e)}', 'error')
        
    return redirect(url_for('stitching.list_services'))

@stitching.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_service(id):
    service = StitchingService.query.get_or_404(id)
    try:
        db.session.delete(service)
        db.session.commit()
        flash('Stitching Service deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting service: {str(e)}', 'error')
        
    return redirect(url_for('stitching.list_services'))
