from flask import Blueprint

# Deprecated shipping routes
# We use /admin/shipping to match the old prefix and avoid conflicts
shipping = Blueprint('shipping', __name__, url_prefix='/admin/shipping')

@shipping.route('/', defaults={'path': ''})
@shipping.route('/<path:path>')
def catch_all(path):
    return "Shipping system is being updated. Please use the new API.", 503
