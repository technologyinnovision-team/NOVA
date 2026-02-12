from flask import Blueprint, request
from models.setting import Setting
from api.utils import success_response, error_response, validate_request_json
from api.middleware import require_api_auth

tax_bp = Blueprint('api_tax', __name__)

@tax_bp.route('/settings', methods=['GET'])
@require_api_auth(optional=True)
def get_tax_settings():
    """Get global tax settings"""
    try:
        enabled = Setting.get('tax_enabled', False)
        prices_include = Setting.get('prices_include_tax', False)
        
        return success_response({
            "enabled": enabled,
            "prices_include_tax": prices_include
        })
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@tax_bp.route('/calculate', methods=['POST'])
@validate_request_json(['subtotal'])
@require_api_auth(optional=True)
def calculate_tax():
    """
    Calculate tax for a cart/order.
    
    Body:
        subtotal (float)
        shipping_cost (float)
        country (str)
        state (str)
        postcode (str)
    """
    try:
        data = request.json
        subtotal = float(data.get('subtotal', 0))
        shipping = float(data.get('shipping_cost', 0))
        country = data.get('country')
        state = data.get('state')
        
        # Check if tax is enabled
        if not Setting.get('tax_enabled', False):
             return success_response({
                "amount": 0.0,
                "rate": 0.0,
                "label": "Tax",
                "included_in_price": False
            })

        # Fetch configured rates (Assuming simplistic structure in settings for now or single global rate)
        # Real-world would likely have a TaxRate model, but we'll use Settings as per exploration
        # Let's check for a "standard_tax_rate" setting
        
        standard_rate = float(Setting.get('standard_tax_rate', 0))
        tax_shipping = Setting.get('tax_shipping', False)
        
        # Simple Logic: Apply standard rate
        # TODO: Implement geo-based lookups if TaxRate model exists or complex JSON structure in settings
        
        taxable_amount = subtotal
        if tax_shipping:
            taxable_amount += shipping
            
        rate_percent = standard_rate
        amount = (taxable_amount * rate_percent) / 100
        
        return success_response({
            "amount": round(amount, 2),
            "rate": rate_percent,
            "label": "Tax",
            "included_in_price": Setting.get('prices_include_tax', False)
        })
        
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)
