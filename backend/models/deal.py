from datetime import datetime
from . import db

class Deal(db.Model):
    __tablename__ = 'deals'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    featured_image = db.Column(db.String(255)) # URL to the featured image
    
    # Relationship to parent product (which holds price, title, image, etc.)
    product = db.relationship('Product', backref=db.backref('deal', uselist=False), lazy=True)
    
    # Slots within this deal
    slots = db.relationship('DealSlot', backref='deal', lazy=True, cascade='all, delete-orphan', order_by='DealSlot.slot_order')

    def __repr__(self):
        return f'<Deal {self.id} for Product {self.product_id}>'

class DealSlot(db.Model):
    __tablename__ = 'deal_slots'
    
    id = db.Column(db.Integer, primary_key=True)
    deal_id = db.Column(db.Integer, db.ForeignKey('deals.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)  # e.g., "Select a Perfume"
    slot_order = db.Column(db.Integer, default=0, nullable=False)
    required_quantity = db.Column(db.Integer, default=1, nullable=False)
    
    # Configuration
    allow_stitching = db.Column(db.Boolean, default=False, nullable=False)
    allow_custom_size = db.Column(db.Boolean, default=False, nullable=False)
    
    # Constraints (what can go in this slot)
    # If empty, implies any product (though usually we restrict by category)
    allowed_categories = db.relationship('Category', secondary='deal_slot_categories', lazy='subquery')
    allowed_products = db.relationship('Product', secondary='deal_slot_products', lazy='subquery')
    
    def __repr__(self):
        return f'<DealSlot {self.title}>'

# Association Tables for Slot Constraints

deal_slot_categories = db.Table('deal_slot_categories',
    db.Column('deal_slot_id', db.Integer, db.ForeignKey('deal_slots.id'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('categories.id'), primary_key=True)
)

deal_slot_products = db.Table('deal_slot_products',
    db.Column('deal_slot_id', db.Integer, db.ForeignKey('deal_slots.id'), primary_key=True),
    db.Column('product_id', db.Integer, db.ForeignKey('products.id'), primary_key=True)
)
