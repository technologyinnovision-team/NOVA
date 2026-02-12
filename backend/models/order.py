from datetime import datetime
from . import db

class Order(db.Model):
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    status = db.Column(db.String(50), default='pending', nullable=False)  # pending, processing, completed, cancelled
    total = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    tax = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    shipping_cost = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    payment_method = db.Column(db.String(50), nullable=True)  # stripe, paypal, cash_on_delivery
    payment_transaction_id = db.Column(db.String(255), nullable=True)  # Stripe payment intent ID, PayPal transaction ID, etc.
    billing_address = db.Column(db.JSON, nullable=True)  # Store complete billing address
    shipping_address = db.Column(db.JSON, nullable=True)  # Store complete shipping address
    coupon_code = db.Column(db.String(50), nullable=True)  # Applied coupon code
    coupon_discount = db.Column(db.Numeric(10, 2), nullable=True)  # Discount amount from coupon
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Deal specific fields
    is_deal_order = db.Column(db.Boolean, default=False)
    deal_id = db.Column(db.Integer, db.ForeignKey('deals.id'), nullable=True)
    deal_data = db.Column(db.JSON, nullable=True)  # Store deal specific metadata (slots, titles, etc)
    
    # Fulfillment Logic
    fulfillment_source = db.Column(db.String(50), default='admin', nullable=False) # admin, pos
    assigned_seller_id = db.Column(db.Integer, db.ForeignKey('pos_seller_profiles.id'), nullable=True)
    assignment_status = db.Column(db.String(50), nullable=True) # pending, assigned, accepted, rejected, timeout, failed
    assignment_attempts = db.Column(db.Integer, default=0)
    assignment_expiry = db.Column(db.DateTime, nullable=True) # When current assignment times out
    
    assignment_expiry = db.Column(db.DateTime, nullable=True) # When current assignment times out
    
    assigned_seller = db.relationship('POSSellerProfile', backref='assigned_orders', lazy=True)
    
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Order {self.order_number}>'

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    variation_id = db.Column(db.Integer, nullable=True)
    variation_details = db.Column(db.JSON, nullable=True)  # Store variation attributes at purchase time (e.g., {"Color": "Silver", "Size": "Medium"})
    product_name = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    original_price = db.Column(db.Numeric(10, 2), nullable=True, default=0.00)
    
    # Stitching Service Details - Removed
    
    # stitching_service = db.relationship('StitchingService', backref='order_items', lazy=True) - Removed
    
    def __repr__(self):
        return f'<OrderItem {self.id}>'

