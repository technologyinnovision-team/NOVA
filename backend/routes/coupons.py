from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import db
from models.coupon import Coupon
from utils.permissions import login_required
from decimal import Decimal
from datetime import datetime
import json

coupons = Blueprint('coupons', __name__, url_prefix='/admin/coupons')

@coupons.route('/')
@login_required
def list():
    """Coupon listing page"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    
    query = Coupon.query
    
    if search:
        query = query.filter(Coupon.code.ilike(f'%{search}%'))
    
    coupons_paginated = query.order_by(Coupon.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('coupons/list.html', 
                         coupons=coupons_paginated,
                         search=search)

@coupons.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create coupon page"""
    if request.method == 'POST':
        try:
            code = request.form.get('code', '').strip().upper()
            if not code:
                flash('Coupon code is required.', 'error')
                return render_template('coupons/form.html', coupon=None)
            
            # Check if code already exists
            if Coupon.query.filter_by(code=code).first():
                flash('Coupon code already exists.', 'error')
                return render_template('coupons/form.html', coupon=None, form_data=request.form)
            
            discount_type = request.form.get('discount_type', 'percentage')
            discount_value = Decimal(request.form.get('discount_value', 0) or 0)
            
            minimum_order = Decimal(request.form.get('minimum_order', 0) or 0) if request.form.get('minimum_order') else None
            maximum_discount = Decimal(request.form.get('maximum_discount', 0) or 0) if request.form.get('maximum_discount') else None
            usage_limit = int(request.form.get('usage_limit', 0) or 0) if request.form.get('usage_limit') else None
            
            expires_at = None
            if request.form.get('expires_at'):
                try:
                    expires_at = datetime.strptime(request.form.get('expires_at'), '%Y-%m-%dT%H:%M')
                except:
                    pass
            
            first_time_only = request.form.get('first_time_only') == 'on'
            enabled = request.form.get('enabled') == 'on'
            
            # Parse product and category restrictions
            product_ids = None
            if request.form.get('product_ids'):
                try:
                    product_ids = [int(pid.strip()) for pid in request.form.get('product_ids').split(',') if pid.strip()]
                except:
                    pass
            
            category_ids = None
            if request.form.get('category_ids'):
                try:
                    category_ids = [int(cid.strip()) for cid in request.form.get('category_ids').split(',') if cid.strip()]
                except:
                    pass
            
            coupon = Coupon(
                code=code,
                discount_type=discount_type,
                discount_value=discount_value,
                minimum_order=minimum_order,
                maximum_discount=maximum_discount,
                usage_limit=usage_limit,
                expires_at=expires_at,
                first_time_only=first_time_only,
                product_ids=product_ids,
                category_ids=category_ids,
                enabled=enabled
            )
            
            db.session.add(coupon)
            db.session.commit()
            
            flash('Coupon created successfully!', 'success')
            return redirect(url_for('coupons.list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating coupon: {str(e)}', 'error')
            print(f"Error: {e}")
    
    return render_template('coupons/form.html', coupon=None)

@coupons.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Edit coupon page"""
    coupon = Coupon.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            code = request.form.get('code', '').strip().upper()
            if not code:
                flash('Coupon code is required.', 'error')
                return render_template('coupons/form.html', coupon=coupon)
            
            # Check if code already exists (excluding current coupon)
            existing = Coupon.query.filter_by(code=code).first()
            if existing and existing.id != coupon.id:
                flash('Coupon code already exists.', 'error')
                return render_template('coupons/form.html', coupon=coupon, form_data=request.form)
            
            coupon.code = code
            coupon.discount_type = request.form.get('discount_type', 'percentage')
            coupon.discount_value = Decimal(request.form.get('discount_value', 0) or 0)
            
            coupon.minimum_order = Decimal(request.form.get('minimum_order', 0) or 0) if request.form.get('minimum_order') else None
            coupon.maximum_discount = Decimal(request.form.get('maximum_discount', 0) or 0) if request.form.get('maximum_discount') else None
            coupon.usage_limit = int(request.form.get('usage_limit', 0) or 0) if request.form.get('usage_limit') else None
            
            expires_at = None
            if request.form.get('expires_at'):
                try:
                    expires_at = datetime.strptime(request.form.get('expires_at'), '%Y-%m-%dT%H:%M')
                except:
                    pass
            coupon.expires_at = expires_at
            
            coupon.first_time_only = request.form.get('first_time_only') == 'on'
            coupon.enabled = request.form.get('enabled') == 'on'
            
            # Parse product and category restrictions
            product_ids = None
            if request.form.get('product_ids'):
                try:
                    product_ids = [int(pid.strip()) for pid in request.form.get('product_ids').split(',') if pid.strip()]
                except:
                    pass
            coupon.product_ids = product_ids
            
            category_ids = None
            if request.form.get('category_ids'):
                try:
                    category_ids = [int(cid.strip()) for cid in request.form.get('category_ids').split(',') if cid.strip()]
                except:
                    pass
            coupon.category_ids = category_ids
            
            db.session.commit()
            
            flash('Coupon updated successfully!', 'success')
            return redirect(url_for('coupons.list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating coupon: {str(e)}', 'error')
            print(f"Error: {e}")
    
    return render_template('coupons/form.html', coupon=coupon)

@coupons.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Delete coupon"""
    coupon = Coupon.query.get_or_404(id)
    
    try:
        db.session.delete(coupon)
        db.session.commit()
        flash('Coupon deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting coupon: {str(e)}', 'error')
    
    return redirect(url_for('coupons.list'))

