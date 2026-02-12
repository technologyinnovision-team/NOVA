from datetime import datetime
from . import db

class Coupon(db.Model):
    """Coupon/Discount code model"""
    __tablename__ = 'coupons'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    discount_type = db.Column(db.String(20), nullable=False)  # percentage, fixed
    discount_value = db.Column(db.Numeric(10, 2), nullable=False)
    minimum_order = db.Column(db.Numeric(10, 2), nullable=True)
    maximum_discount = db.Column(db.Numeric(10, 2), nullable=True)
    usage_limit = db.Column(db.Integer, nullable=True)  # Total usage limit
    usage_count = db.Column(db.Integer, default=0, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)
    first_time_only = db.Column(db.Boolean, default=False, nullable=False)
    product_ids = db.Column(db.JSON, nullable=True)  # Restricted to specific products
    category_ids = db.Column(db.JSON, nullable=True)  # Restricted to specific categories
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Coupon {self.code}>'
    
    def is_valid(self, order_total=0, product_ids=None, category_ids=None, customer_id=None):
        """Check if coupon is valid for use"""
        if not self.enabled:
            return False, "Coupon is disabled"
        
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False, "Coupon has expired"
        
        if self.usage_limit and self.usage_count >= self.usage_limit:
            return False, "Coupon usage limit reached"
        
        if self.minimum_order and order_total < float(self.minimum_order):
            return False, f"Minimum order amount of ${self.minimum_order} required"
        
        # Check product restrictions
        if self.product_ids and product_ids:
            if not any(pid in self.product_ids for pid in product_ids):
                return False, "Coupon not valid for selected products"
        
        # Check category restrictions
        if self.category_ids and category_ids:
            if not any(cid in self.category_ids for cid in category_ids):
                return False, "Coupon not valid for selected categories"
        
        return True, "Valid"
    
    def calculate_discount(self, order_total):
        """Calculate discount amount"""
        if self.discount_type == 'percentage':
            discount = float(order_total) * (float(self.discount_value) / 100)
            if self.maximum_discount:
                discount = min(discount, float(self.maximum_discount))
        else:  # fixed
            discount = min(float(self.discount_value), float(order_total))
        
        return round(discount, 2)
    
    def apply(self):
        """Increment usage count"""
        self.usage_count += 1
        self.updated_at = datetime.utcnow()

