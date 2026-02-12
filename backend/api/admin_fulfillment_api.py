from flask import Blueprint, request, jsonify
from models import db
from models.order import Order
from models.pos import POSSellerProfile
from services.fulfillment_service import FulfillmentService
from utils.permissions import admin_required

admin_fulfillment_bp = Blueprint('admin_fulfillment_api', __name__, url_prefix='/api/admin/fulfillment')

@admin_fulfillment_bp.route('/dashboard', methods=['GET'])
@admin_required
def dashboard():
    """
    Overview of fulfillment status.
    """
    pending_assignment = Order.query.filter_by(fulfillment_source='pos', assignment_status='assigned').count()
    failed_assignments = Order.query.filter_by(fulfillment_source='admin').count() # Admin fallback count
    
    return jsonify({
        'pending_pos_acceptance': pending_assignment,
        'admin_fallback_orders': failed_assignments
    })

@admin_fulfillment_bp.route('/override', methods=['POST'])
@admin_required
def override_assignment():
    """
    Force assign an order to Admin or specific POS.
    """
    data = request.get_json()
    order_id = data.get('order_id')
    target = data.get('target') # 'admin' or 'pos'
    seller_id = data.get('seller_id') # if target is pos
    
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404
        
    try:
        if target == 'admin':
            # Release old stock if any
            if order.assigned_seller_id:
                # Logic to release stock from old seller...
                # Ideally move this release logic to a helper in Service
                pass
                
            FulfillmentService.fallback_to_admin(order)
            return jsonify({'message': 'Forced assignment to Admin'})
            
        elif target == 'pos' and seller_id:
            # Force specific POS (Bypassing geo logic?)
            # This requires custom logic not yet in FulfillmentService generic assign_order
            return jsonify({'error': 'Manual POS assignment not yet implemented'}), 501
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500
