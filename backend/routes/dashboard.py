from flask import Blueprint, render_template
from models import db
from models.product import Product
from models.customer import Customer
from models.order import Order
from models.pos import POSSellerProfile
from utils.permissions import login_required

dashboard = Blueprint('dashboard', __name__, url_prefix='/admin')

@dashboard.route('/')
@dashboard.route('/dashboard')
@login_required
def index():
    """Dashboard overview page"""
    # Get statistics
    total_products = Product.query.count()
    published_products = Product.query.filter_by(status='published').count()
    total_customers = Customer.query.count()
    total_orders = Order.query.count()
    
    # Fulfillment Statistics
    pos_assigned_orders = Order.query.filter_by(fulfillment_source='pos', assignment_status='assigned').count()
    pos_accepted_orders = Order.query.filter_by(fulfillment_source='pos', assignment_status='accepted').count()
    admin_fallback_orders = Order.query.filter_by(fulfillment_source='admin').count()
    total_pos_sellers = POSSellerProfile.query.filter_by(is_active=True).count()
    
    # Recent products
    recent_products = Product.query.order_by(Product.created_at.desc()).limit(5).all()
    
    # Recent orders
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    
    # Pending POS assignments
    pending_pos_orders = Order.query.filter_by(
        fulfillment_source='pos', 
        assignment_status='assigned'
    ).order_by(Order.created_at.desc()).limit(10).all()
    
    stats = {
        'total_products': total_products,
        'published_products': published_products,
        'draft_products': total_products - published_products,
        'total_customers': total_customers,
        'total_orders': total_orders,
        'pos_assigned': pos_assigned_orders,
        'pos_accepted': pos_accepted_orders,
        'admin_fallback': admin_fallback_orders,
        'total_pos_sellers': total_pos_sellers,
    }
    
    return render_template('dashboard/index.html', 
                         stats=stats, 
                         recent_products=recent_products, 
                         recent_orders=recent_orders,
                         pending_pos_orders=pending_pos_orders)
