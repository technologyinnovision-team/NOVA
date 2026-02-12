from flask import Blueprint, request, jsonify
from models import db
from models.shipping import ShippingZone, ShippingZoneLocation, ShippingMethod
from api.utils import success_response, error_response
from api.middleware import require_api_auth

shipping_bp = Blueprint('api_shipping', __name__)

# --- ZONES ---

@shipping_bp.route('/zones', methods=['GET'])
@require_api_auth(optional=False)
def get_zones():
    """Get all shipping zones"""
    try:
        zones = ShippingZone.query.order_by(ShippingZone.zone_order.asc()).all()
        return success_response([zone.to_dict() for zone in zones])
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@shipping_bp.route('/zones', methods=['POST'])
@require_api_auth(optional=False)
def create_zone():
    """Create a new shipping zone"""
    try:
        data = request.json
        name = data.get('name')
        
        if not name:
            return error_response("Name is required", "VALIDATION_ERROR", 400)
            
        zone = ShippingZone(name=name, zone_order=data.get('zone_order', 0))
        db.session.add(zone)
        db.session.commit()
        
        return success_response(zone.to_dict(), 201)
    except Exception as e:
        db.session.rollback()
        return error_response(str(e), "INTERNAL_ERROR", 500)

@shipping_bp.route('/zones/<int:zone_id>', methods=['GET'])
@require_api_auth(optional=False)
def get_zone(zone_id):
    """Get a specific zone"""
    try:
        zone = ShippingZone.query.get(zone_id)
        if not zone:
            return error_response("Zone not found", "NOT_FOUND", 404)
            
        return success_response(zone.to_dict())
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@shipping_bp.route('/zones/<int:zone_id>', methods=['PUT'])
@require_api_auth(optional=False)
def update_zone(zone_id):
    """Update a zone"""
    try:
        zone = ShippingZone.query.get(zone_id)
        if not zone:
            return error_response("Zone not found", "NOT_FOUND", 404)
            
        data = request.json
        if 'name' in data:
            zone.name = data['name']
        if 'zone_order' in data:
            zone.zone_order = data['zone_order']
            
        db.session.commit()
        return success_response(zone.to_dict())
    except Exception as e:
        db.session.rollback()
        return error_response(str(e), "INTERNAL_ERROR", 500)

@shipping_bp.route('/zones/<int:zone_id>', methods=['DELETE'])
@require_api_auth(optional=False)
def delete_zone(zone_id):
    """Delete a zone"""
    try:
        zone = ShippingZone.query.get(zone_id)
        if not zone:
            return error_response("Zone not found", "NOT_FOUND", 404)
            
        db.session.delete(zone)
        db.session.commit()
        return success_response({'message': 'Zone deleted'})
    except Exception as e:
        db.session.rollback()
        return error_response(str(e), "INTERNAL_ERROR", 500)

# --- LOCATIONS ---

@shipping_bp.route('/zones/<int:zone_id>/locations', methods=['POST'])
@require_api_auth(optional=False)
def update_zone_locations(zone_id):
    """Update locations for a zone (Replace all)"""
    try:
        zone = ShippingZone.query.get(zone_id)
        if not zone:
            return error_response("Zone not found", "NOT_FOUND", 404)
            
        data = request.json
        locations = data.get('locations', [])
        
        # Clear existing
        ShippingZoneLocation.query.filter_by(zone_id=zone_id).delete()
        
        for loc in locations:
            new_loc = ShippingZoneLocation(
                zone_id=zone_id,
                location_code=loc.get('code'),
                location_type=loc.get('type')
            )
            db.session.add(new_loc)
            
        db.session.commit()
        return success_response(zone.to_dict())
    except Exception as e:
        db.session.rollback()
        return error_response(str(e), "INTERNAL_ERROR", 500)

# --- METHODS ---

@shipping_bp.route('/zones/<int:zone_id>/methods', methods=['POST'])
@require_api_auth(optional=False)
def add_method(zone_id):
    """Add a shipping method to a zone"""
    try:
        zone = ShippingZone.query.get(zone_id)
        if not zone:
            return error_response("Zone not found", "NOT_FOUND", 404)
            
        data = request.json
        method = ShippingMethod(
            zone_id=zone_id,
            title=data.get('title'),
            method_id=data.get('method_id'), # flat_rate, free_shipping, local_pickup
            enabled=data.get('enabled', True),
            tax_status=data.get('tax_status', 'taxable'),
            cost=data.get('cost', 0),
            description=data.get('description'),
            requirements=data.get('requirements'),
            min_order_amount=data.get('min_order_amount'),
            order=data.get('order', 0)
        )
        db.session.add(method)
        db.session.commit()
        return success_response(method.to_dict(), 201)
    except Exception as e:
        db.session.rollback()
        return error_response(str(e), "INTERNAL_ERROR", 500)

@shipping_bp.route('/methods/<int:method_id>', methods=['PUT'])
@require_api_auth(optional=False)
def update_method(method_id):
    """Update a shipping method"""
    try:
        method = ShippingMethod.query.get(method_id)
        if not method:
            return error_response("Method not found", "NOT_FOUND", 404)
            
        data = request.json
        # Bulk update attributes
        allowed_fields = ['title', 'method_id', 'enabled', 'tax_status', 'cost', 'description', 'requirements', 'min_order_amount', 'order']
        for field in allowed_fields:
            if field in data:
                setattr(method, field, data[field])
                
        db.session.commit()
        return success_response(method.to_dict())
    except Exception as e:
        db.session.rollback()
        return error_response(str(e), "INTERNAL_ERROR", 500)

@shipping_bp.route('/methods/<int:method_id>', methods=['DELETE'])
@require_api_auth(optional=False)
def delete_method(method_id):
    """Delete a shipping method"""
    try:
        method = ShippingMethod.query.get(method_id)
        if not method:
            return error_response("Method not found", "NOT_FOUND", 404)
            
        db.session.delete(method)
        db.session.commit()
        return success_response({'message': 'Method deleted'})
    except Exception as e:
        db.session.rollback()
        return error_response(str(e), "INTERNAL_ERROR", 500)

@shipping_bp.route('/calculate', methods=['POST'])
@require_api_auth(optional=False)
def calculate_shipping():
    """
    Calculate shipping methods based on location and cart total.
    """
    try:
        data = request.json
        country = data.get('country')
        state = data.get('state')
        cart_total = float(data.get('cart_total', 0))
        
        # Logic to find matching zones
        # 1. Find zones matching country AND state
        # 2. Find zones matching country (no state specific)
        # 3. Find zones matching 'Rest of World' (if implemented, usually * or specific code)
        
        # Priority: State match > Country match > generic
        
        # Fetch all zones to filter in python or do complex query
        # Given simpler model:
        
        # Find zone locations matching our criteria
        # A location matches if code == country OR code == state
        # We need to map back to zones.
        
        # Better: get all zones sorted by order. Iterate and check if location matches.
        zones = ShippingZone.query.order_by(ShippingZone.zone_order.asc()).all()
        
        matched_zone = None
        
        # Simple matching logic
        for zone in zones:
            # Get locations for this zone
            locs = zone.locations
            if not locs:
                continue # Skip zones with no locations? or treats as everywhere? usually empty = nowhere.
            
            # Check for exact state match first if state provided
            if state:
                state_match = any(l.location_code == state and l.location_type == 'state' for l in locs)
                if state_match:
                    matched_zone = zone
                    break
            
            # Check for country match
            country_match = any(l.location_code == country and l.location_type == 'country' for l in locs)
            if country_match:
                matched_zone = zone
                break
                
        if not matched_zone:
            # Maybe a catch-all zone?
            # For now return empty
            return success_response({'methods': []})
            
        # Get methods for matched zone
        methods = []
        for method in matched_zone.methods:
            if not method.enabled:
                continue
                
            # Check requirements
            if method.min_order_amount:
                if cart_total < float(method.min_order_amount):
                    continue
                    
            methods.append(method.to_dict())
            
        # Sort methods by order
        methods.sort(key=lambda x: x['order'])
            
        return success_response({'methods': methods})
        
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

