from flask import Blueprint, request
from models import db
from models.coupon import Coupon
from api.utils import success_response, error_response, validate_request_json
from datetime import datetime

coupons_bp = Blueprint('coupons', __name__)

@coupons_bp.route('/validate', methods=['POST'])
@validate_request_json(['code'])
def validate_coupon():
    """Validate coupon code"""
    try:
        data = request.get_json()
        code = data.get('code', '').strip().upper()
        order_total = float(data.get('order_total', 0))
        product_ids = data.get('product_ids', [])
        category_ids = data.get('category_ids', [])
        customer_id = data.get('customer_id')
        
        if not code:
            return error_response("Coupon code is required", "MISSING_CODE", 400)
        
        coupon = Coupon.query.filter_by(code=code).first()
        
        if not coupon:
            return error_response("Invalid coupon code", "INVALID_COUPON", 404)
        
        # Validate coupon
        is_valid, message = coupon.is_valid(
            order_total=order_total,
            product_ids=product_ids,
            category_ids=category_ids,
            customer_id=customer_id
        )
        
        if not is_valid:
            return error_response(message, "COUPON_INVALID", 400)
        
        # Calculate discount
        discount_amount = coupon.calculate_discount(order_total)
        final_total = order_total - discount_amount
        
        return success_response({
            "valid": True,
            "code": coupon.code,
            "discount_type": coupon.discount_type,
            "discount_value": float(coupon.discount_value),
            "discount_amount": discount_amount,
            "original_total": order_total,
            "final_total": final_total,
            "minimum_order": float(coupon.minimum_order) if coupon.minimum_order else None,
            "maximum_discount": float(coupon.maximum_discount) if coupon.maximum_discount else None
        })
        
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

