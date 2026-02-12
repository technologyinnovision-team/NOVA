from flask import Blueprint, request, session
from models import db
from models.product import Product, ProductVariation

from api.utils import success_response, error_response, validate_request_json
from datetime import datetime
import uuid

cart_bp = Blueprint('cart', __name__)

def get_or_create_session_id():
    """Get or create a session ID for cart"""
    if 'cart_session_id' not in session:
        session['cart_session_id'] = str(uuid.uuid4())
    return session['cart_session_id']

def get_cart_from_session():
    """Get cart from session or return empty cart"""
    session_id = get_or_create_session_id()
    cart_key = f'cart_{session_id}'
    return session.get(cart_key, {'items': [], 'updated_at': str(datetime.utcnow())})

def save_cart_to_session(cart_data):
    """Save cart to session"""
    session_id = get_or_create_session_id()
    cart_key = f'cart_{session_id}'
    cart_data['updated_at'] = str(datetime.utcnow())
    session[cart_key] = cart_data
    session.modified = True

def calculate_cart_totals(cart_items):
    """Calculate subtotal, shipping, tax, and total for cart items"""
    subtotal = 0.0
    
    for item in cart_items:
        product_id = item.get('product_id')
        variation_id = item.get('variation_id')
        quantity = item.get('quantity', 1)
        
        # Get product
        product = Product.query.get(product_id)
        if not product:
            continue
        
        # Get price (from variation if available, otherwise from product)
        price = 0.0
        if variation_id:
            variation = ProductVariation.query.filter_by(
                id=variation_id,
                product_id=product_id
            ).first()
            if variation:
                price = float(variation.sale_price or variation.regular_price or 0)
        else:
            price = float(product.sale_price or product.regular_price or 0)
            
        # Stitching removed

        
        subtotal += price * quantity
    
    # For now, shipping and tax are 0 (can be calculated later based on settings)
    shipping = 0.0
    tax = 0.0
    total = subtotal + shipping + tax
    
    return {
        'subtotal': round(subtotal, 2),
        'shipping': round(shipping, 2),
        'tax': round(tax, 2),
        'total': round(total, 2)
    }

def format_cart_item(item, product=None, variation=None):
    """Format cart item with product details"""
    if not product:
        product = Product.query.get(item.get('product_id'))
    
    if not product:
        return None
    
    variation_id = item.get('variation_id')
    if variation_id and not variation:
        variation = ProductVariation.query.filter_by(
            id=variation_id,
            product_id=product.id
        ).first()
    
    # Get price
    price = 0.0
    if variation:
        price = float(variation.sale_price or variation.regular_price or 0)
    else:
        price = float(product.sale_price or product.regular_price or 0)
    
    # Format product data
    product_data = {
        'id': product.id,
        'title': product.title,
        'name': product.title,
        'slug': product.slug,
        'image': product.primary_image,
        'images': [img.image_url for img in product.images[:3]] if product.images else [],
        'price': float(product.regular_price) if product.regular_price else 0.0,
        'regular_price': float(product.regular_price) if product.regular_price else 0.0,
        'sale_price': float(product.sale_price) if product.sale_price else None,
        'stock_status': product.stock_status,
        'stock_quantity': product.stock_quantity
    }
    
    # Format variation data if available
    variation_data = None
    if variation:
        variation_data = {
            'id': variation.id,
            'price': float(variation.regular_price) if variation.regular_price else 0.0,
            'regular_price': float(variation.regular_price) if variation.regular_price else 0.0,
            'sale_price': float(variation.sale_price) if variation.sale_price else None,
            'stock_status': variation.stock_status,
            'stock_quantity': variation.stock_quantity,
            'attributes': variation.attribute_terms if variation.attribute_terms else {}
        }
    
    return {
        'product_id': product.id,
        'variation_id': variation_id,
        'quantity': item.get('quantity', 1),
        'price': price,
        'product': product_data,
        'selectedVariation': variation_data,
        'selectedAttributes': variation.attribute_terms if variation and variation.attribute_terms else {}
    }

@cart_bp.route('', methods=['GET'])
def get_cart():
    """Get current cart"""
    try:
        cart_data = get_cart_from_session()
        cart_items = cart_data.get('items', [])
        
        # Format cart items with product details
        formatted_items = []
        for item in cart_items:
            formatted_item = format_cart_item(item)
            if formatted_item:
                formatted_items.append(formatted_item)
        
        # Calculate totals
        totals = calculate_cart_totals(cart_items)
        
        cart_response = {
            'items': formatted_items,
            'subtotal': totals['subtotal'],
            'shipping': totals['shipping'],
            'tax': totals['tax'],
            'total': totals['total']
        }
        
        return success_response(cart_response)
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@cart_bp.route('', methods=['POST'])
@validate_request_json(['product_id', 'quantity'])
def add_to_cart():
    """Add item to cart"""
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        quantity = int(data.get('quantity', 1))
        variation_id = data.get('variation_id')
        attributes = data.get('attributes', [])

        
        # Validate product
        product = Product.query.get(product_id)
        if not product:
            return error_response("Product not found", "PRODUCT_NOT_FOUND", 404)
        
        # Stitching validation removed

        
        # Validate variation if provided
        if variation_id:
            variation = ProductVariation.query.filter_by(
                id=variation_id,
                product_id=product_id
            ).first()
            if not variation:
                return error_response("Variation not found", "VARIATION_NOT_FOUND", 404)
            
            # Check stock for variation
            if variation.manage_stock and variation.stock_quantity < quantity:
                return error_response(
                    f"Insufficient stock. Only {variation.stock_quantity} available",
                    "INSUFFICIENT_STOCK",
                    400
                )
        else:
            # Check stock for product
            if product.manage_stock and product.stock_quantity < quantity:
                return error_response(
                    f"Insufficient stock. Only {product.stock_quantity} available",
                    "INSUFFICIENT_STOCK",
                    400
                )
        
        # Validate quantity
        if quantity <= 0:
            return error_response("Quantity must be greater than 0", "INVALID_QUANTITY", 400)
        
        # Get cart from session
        cart_data = get_cart_from_session()
        cart_items = cart_data.get('items', [])
        
        # Check if item already exists in cart matches product, variation AND stitching option
        existing_item_index = None
        for i, item in enumerate(cart_items):
            if item.get('product_id') == product_id:
                # Check variation match
                var_match = False
                if variation_id:
                    if item.get('variation_id') == variation_id:
                        var_match = True
                else:
                    if not item.get('variation_id'):
                        var_match = True
                
                if var_match:
                    existing_item_index = i
                    break
        
        if existing_item_index is not None:
            # Update quantity of existing item
            new_quantity = cart_items[existing_item_index]['quantity'] + quantity
            cart_items[existing_item_index]['quantity'] = new_quantity
        else:
            # Add new item
            new_item = {
                'product_id': product_id,
                'variation_id': variation_id,
                'quantity': quantity,
                'attributes': attributes,

            }
            cart_items.append(new_item)
        
        # Save cart to session
        cart_data['items'] = cart_items
        save_cart_to_session(cart_data)
        
        # Format response
        formatted_items = []
        for item in cart_items:
            formatted_item = format_cart_item(item)
            if formatted_item:
                formatted_items.append(formatted_item)
        
        totals = calculate_cart_totals(cart_items)
        
        cart_response = {
            'items': formatted_items,
            'subtotal': totals['subtotal'],
            'shipping': totals['shipping'],
            'tax': totals['tax'],
            'total': totals['total']
        }
        
        return success_response(cart_response, "Item added to cart", 201)
    except ValueError as e:
        return error_response(f"Invalid input: {str(e)}", "INVALID_INPUT", 400)
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@cart_bp.route('', methods=['PUT'])
@validate_request_json(['product_id', 'quantity'])
def update_cart():
    """Update item quantity in cart"""
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        quantity = int(data.get('quantity', 1))
        variation_id = data.get('variation_id')
        
        # Validate quantity
        if quantity <= 0:
            return error_response("Quantity must be greater than 0", "INVALID_QUANTITY", 400)
        
        # Get cart from session
        cart_data = get_cart_from_session()
        cart_items = cart_data.get('items', [])
        
        # Find item in cart
        item_found = False
        for item in cart_items:
            if item.get('product_id') == product_id:
                if variation_id:
                    if item.get('variation_id') == variation_id:
                        # Check stock
                        variation = ProductVariation.query.filter_by(
                            id=variation_id,
                            product_id=product_id
                        ).first()
                        if variation and variation.manage_stock and variation.stock_quantity < quantity:
                            return error_response(
                                f"Insufficient stock. Only {variation.stock_quantity} available",
                                "INSUFFICIENT_STOCK",
                                400
                            )
                        item['quantity'] = quantity
                        item_found = True
                        break
                else:
                    if not item.get('variation_id'):
                        # Check stock
                        product = Product.query.get(product_id)
                        if product and product.manage_stock and product.stock_quantity < quantity:
                            return error_response(
                                f"Insufficient stock. Only {product.stock_quantity} available",
                                "INSUFFICIENT_STOCK",
                                400
                            )
                        item['quantity'] = quantity
                        item_found = True
                        break
        
        if not item_found:
            return error_response("Item not found in cart", "ITEM_NOT_FOUND", 404)
        
        # Save cart to session
        cart_data['items'] = cart_items
        save_cart_to_session(cart_data)
        
        # Format response
        formatted_items = []
        for item in cart_items:
            formatted_item = format_cart_item(item)
            if formatted_item:
                formatted_items.append(formatted_item)
        
        totals = calculate_cart_totals(cart_items)
        
        cart_response = {
            'items': formatted_items,
            'subtotal': totals['subtotal'],
            'shipping': totals['shipping'],
            'tax': totals['tax'],
            'total': totals['total']
        }
        
        return success_response(cart_response, "Cart updated")
    except ValueError as e:
        return error_response(f"Invalid input: {str(e)}", "INVALID_INPUT", 400)
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@cart_bp.route('', methods=['DELETE'])
def remove_from_cart():
    """Remove item from cart or clear entire cart"""
    try:
        data = request.get_json() or {}
        product_id = data.get('product_id')
        variation_id = data.get('variation_id')
        
        # Get cart from session
        cart_data = get_cart_from_session()
        cart_items = cart_data.get('items', [])
        
        # If no product_id provided, clear entire cart
        if not product_id:
            cart_items = []
        else:
            # Remove specific item
            cart_items = [
                item for item in cart_items
                if not (
                    item.get('product_id') == product_id and
                    (
                        (variation_id and item.get('variation_id') == variation_id) or
                        (not variation_id and not item.get('variation_id'))
                    )
                )
            ]
        
        # Save cart to session
        cart_data['items'] = cart_items
        save_cart_to_session(cart_data)
        
        # Format response
        formatted_items = []
        for item in cart_items:
            formatted_item = format_cart_item(item)
            if formatted_item:
                formatted_items.append(formatted_item)
        
        totals = calculate_cart_totals(cart_items)
        
        cart_response = {
            'items': formatted_items,
            'subtotal': totals['subtotal'],
            'shipping': totals['shipping'],
            'tax': totals['tax'],
            'total': totals['total']
        }
        
        message = "Cart cleared" if not product_id else "Item removed from cart"
        return success_response(cart_response, message)
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)

@cart_bp.route('/sync', methods=['POST'])
@validate_request_json(['session_id', 'cart_items'])
def sync_cart():
    """Sync cart with session (legacy endpoint for compatibility)"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        cart_items = data.get('cart_items', [])
        
        # Store cart in session
        if session_id:
            session['cart_session_id'] = session_id
            cart_key = f'cart_{session_id}'
            session[cart_key] = {
                'items': cart_items,
                'updated_at': str(datetime.utcnow())
            }
            session.modified = True
        
        return success_response({
            "session_id": session_id,
            "synced": True
        }, "Cart synced successfully")
    except Exception as e:
        return error_response(str(e), "INTERNAL_ERROR", 500)
