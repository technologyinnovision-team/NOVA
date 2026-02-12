from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import db
from models.shipping import ShippingZone, ShippingZoneLocation, ShippingMethod
from utils.permissions import login_required
from utils.countries import COUNTRIES
import json

shipping_admin = Blueprint('shipping_admin', __name__, url_prefix='/admin/shipping')

@shipping_admin.route('/')
@shipping_admin.route('/zones')
@login_required
def zones():
    """Shipping zones management page"""
    zones = ShippingZone.query.order_by(ShippingZone.zone_order).all()
    return render_template('shipping/zones.html', zones=zones)

@shipping_admin.route('/zones/create', methods=['GET', 'POST'])
@login_required
def create_zone():
    """Create a new shipping zone"""
    if request.method == 'POST':
        try:
            zone = ShippingZone(
                name=request.form.get('name'),
                zone_order=int(request.form.get('zone_order', 0))
            )
            db.session.add(zone)
            db.session.commit()
            
            # Add locations if provided
            locations_json = request.form.get('locations')
            if locations_json:
                locations = json.loads(locations_json)
                for loc in locations:
                    location = ShippingZoneLocation(
                        zone_id=zone.id,
                        location_code=loc['code'],
                        location_type=loc['type']
                    )
                    db.session.add(location)
                db.session.commit()
            
            flash('Shipping zone created successfully!', 'success')
            return redirect(url_for('shipping_admin.zones'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating zone: {str(e)}', 'error')
    
    return render_template('shipping/zone_form.html', zone=None, countries=COUNTRIES)

@shipping_admin.route('/zones/<int:zone_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_zone(zone_id):
    """Edit a shipping zone"""
    zone = ShippingZone.query.get_or_404(zone_id)
    
    if request.method == 'POST':
        try:
            zone.name = request.form.get('name')
            zone.zone_order = int(request.form.get('zone_order', 0))
            
            # Update locations
            # First, remove all existing locations
            ShippingZoneLocation.query.filter_by(zone_id=zone.id).delete()
            
            # Add new locations
            locations_json = request.form.get('locations')
            if locations_json:
                locations = json.loads(locations_json)
                for loc in locations:
                    location = ShippingZoneLocation(
                        zone_id=zone.id,
                        location_code=loc['code'],
                        location_type=loc['type']
                    )
                    db.session.add(location)
            
            db.session.commit()
            flash('Shipping zone updated successfully!', 'success')
            return redirect(url_for('shipping_admin.zones'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating zone: {str(e)}', 'error')
    
    return render_template('shipping/zone_form.html', zone=zone, countries=COUNTRIES)

@shipping_admin.route('/zones/<int:zone_id>/delete', methods=['POST'])
@login_required
def delete_zone(zone_id):
    """Delete a shipping zone"""
    try:
        zone = ShippingZone.query.get_or_404(zone_id)
        db.session.delete(zone)
        db.session.commit()
        flash('Shipping zone deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting zone: {str(e)}', 'error')
    
    return redirect(url_for('shipping_admin.zones'))

@shipping_admin.route('/zones/<int:zone_id>/methods/create', methods=['GET', 'POST'])
@login_required
def create_method(zone_id):
    """Create a new shipping method for a zone"""
    zone = ShippingZone.query.get_or_404(zone_id)
    
    if request.method == 'POST':
        try:
            method = ShippingMethod(
                zone_id=zone_id,
                title=request.form.get('title'),
                method_id=request.form.get('method_id', 'flat_rate'),
                enabled=request.form.get('enabled') == 'on',
                order=int(request.form.get('method_order', 0)),
                cost=float(request.form.get('cost', 0)),
                min_order_amount=float(request.form.get('min_amount', 0)) if request.form.get('min_amount') else None,
                tax_status=request.form.get('tax_status', 'taxable'),
                requirements=request.form.get('requirements')
            )
            db.session.add(method)
            db.session.commit()
            flash('Shipping method created successfully!', 'success')
            return redirect(url_for('shipping_admin.zones'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating method: {str(e)}', 'error')
    
    return render_template('shipping/method_form.html', zone=zone, method=None)

@shipping_admin.route('/methods/<int:method_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_method(method_id):
    """Edit a shipping method"""
    method = ShippingMethod.query.get_or_404(method_id)
    zone = ShippingZone.query.get_or_404(method.zone_id)
    
    if request.method == 'POST':
        try:
            method.title = request.form.get('title')
            method.method_id = request.form.get('method_id', 'flat_rate')
            method.enabled = request.form.get('enabled') == 'on'
            method.order = int(request.form.get('method_order', 0))
            method.cost = float(request.form.get('cost', 0))
            method.min_order_amount = float(request.form.get('min_amount', 0)) if request.form.get('min_amount') else None
            method.tax_status = request.form.get('tax_status', 'taxable')
            method.requirements = request.form.get('requirements')
            
            db.session.commit()
            flash('Shipping method updated successfully!', 'success')
            return redirect(url_for('shipping_admin.zones'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating method: {str(e)}', 'error')
    
    return render_template('shipping/method_form.html', zone=zone, method=method)

@shipping_admin.route('/methods/<int:method_id>/delete', methods=['POST'])
@login_required
def delete_method(method_id):
    """Delete a shipping method"""
    try:
        method = ShippingMethod.query.get_or_404(method_id)
        db.session.delete(method)
        db.session.commit()
        flash('Shipping method deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting method: {str(e)}', 'error')
    
    return redirect(url_for('shipping_admin.zones'))
