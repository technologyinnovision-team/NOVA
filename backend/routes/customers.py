from flask import Blueprint, render_template
from models.customer import Customer
from utils.permissions import login_required

customers = Blueprint('customers', __name__, url_prefix='/admin/customers')

@customers.route('/')
@login_required
def list():
    """Customer listing page"""
    customers_list = Customer.query.order_by(Customer.created_at.desc()).limit(50).all()
    return render_template('customers/list.html', customers=customers_list)

