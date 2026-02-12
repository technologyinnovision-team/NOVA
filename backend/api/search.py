from flask import Blueprint, request
from sqlalchemy import or_, and_, desc
from models.product import Product
from api.middleware import require_api_auth
from api.utils import success_response, error_response
from api.products import format_product, base_product_query

search_bp = Blueprint('search', __name__)

@search_bp.route('/search-products', methods=['GET'])
@require_api_auth(optional=False)
def search_products():
    """
    Search products by keyword.
    
    Query Params:
        query (str): Search term (min 2 chars).
        per_page (int): Limit results.
    """
    try:
        query_str = request.args.get('query', '').strip()
        per_page = min(request.args.get('per_page', 8, type=int), 50)
        
        if not query_str or len(query_str) < 2:
            return success_response({"products": []})
        
        # Use optimized base query
        query = base_product_query().filter(
            or_(
                Product.title.ilike(f'%{query_str}%'),
                Product.description.ilike(f'%{query_str}%'),
                Product.short_description.ilike(f'%{query_str}%'),
                Product.sku.ilike(f'%{query_str}%')
            )
        ).limit(per_page)
        
        products = [format_product(p) for p in query.all()]
        
        return success_response({
            "products": products,
            "meta": {
                "count": len(products),
                "query": query_str
            }
        })
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)
