from datetime import datetime
from . import db

class POSSellerProfile(db.Model):
    __tablename__ = 'pos_seller_profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    business_name = db.Column(db.String(255), nullable=False)
    
    # Address & Location
    address_line1 = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    zip_code = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    
    # Geolocation for Distance Calculation
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    
    # Operational Status
    is_active = db.Column(db.Boolean, default=True, nullable=False) # Master switch
    auto_accept_orders = db.Column(db.Boolean, default=False, nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('pos_profile', uselist=False))

    def __repr__(self):
        return f'<POSSellerProfile {self.business_name}>'

class POSInventory(db.Model):
    __tablename__ = 'pos_inventory'
    
    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('pos_seller_profiles.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    variation_id = db.Column(db.Integer, db.ForeignKey('product_variations.id'), nullable=True)
    
    # Stock Levels
    quantity = db.Column(db.Integer, default=0, nullable=False)
    reserved_quantity = db.Column(db.Integer, default=0, nullable=False) # Locked for pending orders
    
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    seller = db.relationship('POSSellerProfile', backref='inventory')
    product = db.relationship('Product', backref='pos_inventory')
    variation = db.relationship('ProductVariation', backref='pos_inventory')
    
    __table_args__ = (
        db.UniqueConstraint('seller_id', 'product_id', 'variation_id', name='uq_pos_inventory_item'),
    )

    def __repr__(self):
        return f'<POSInventory Seller:{self.seller_id} Product:{self.product_id} Var:{self.variation_id} Qty:{self.quantity}>'
