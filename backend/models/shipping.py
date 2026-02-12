from datetime import datetime
from . import db

class ShippingZone(db.Model):
    """Shipping zones for geographic regions"""
    __tablename__ = 'shipping_zones'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    # Order of matching (lower number = higher priority)
    zone_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    locations = db.relationship('ShippingZoneLocation', backref='zone', lazy=True, cascade='all, delete-orphan')
    methods = db.relationship('ShippingMethod', backref='zone', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'zone_order': self.zone_order,
            'locations': [loc.to_dict() for loc in self.locations],
            'methods': [method.to_dict() for method in self.methods]
        }

    def __repr__(self):
        return f'<ShippingZone {self.name}>'

class ShippingZoneLocation(db.Model):
    """Location entries for shipping zones (countries, states, postcodes)"""
    __tablename__ = 'shipping_zone_locations'
    
    id = db.Column(db.Integer, primary_key=True)
    zone_id = db.Column(db.Integer, db.ForeignKey('shipping_zones.id'), nullable=False)
    location_code = db.Column(db.String(100), nullable=False)  # ISO Country Code (US) or State Code (US:CA)
    location_type = db.Column(db.String(50), nullable=False) # country, state
    
    def to_dict(self):
        return {
            'code': self.location_code,
            'type': self.location_type
        }

    def __repr__(self):
        return f'<ShippingZoneLocation {self.location_code}>'

class ShippingMethod(db.Model):
    __tablename__ = 'shipping_methods'
    
    id = db.Column(db.Integer, primary_key=True)
    zone_id = db.Column(db.Integer, db.ForeignKey('shipping_zones.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    method_id = db.Column(db.String(50), nullable=False) # flat_rate, free_shipping, local_pickup
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    order = db.Column(db.Integer, default=0, nullable=False)
    tax_status = db.Column(db.String(20), default='taxable', nullable=False) # taxable, none
    cost = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    description = db.Column(db.Text, nullable=True)
    requirements = db.Column(db.String(50), nullable=True) # min_amount, coupon, etc.
    min_order_amount = db.Column(db.Numeric(10, 2), nullable=True) # If requirement is min_amount
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'method_id': self.method_id,
            'enabled': self.enabled,
            'order': self.order,
            'tax_status': self.tax_status,
            'cost': float(self.cost),
            'description': self.description,
            'requirements': self.requirements,
            'min_order_amount': float(self.min_order_amount) if self.min_order_amount else None
        }

    def __repr__(self):
        return f'<ShippingMethod {self.title}>'

class ShippingClass(db.Model):
    """Shipping classes for product-specific shipping rates (Preserved)"""
    __tablename__ = 'shipping_classes'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'description': self.description,
            'count': len(self.products) if hasattr(self, 'products') else 0
        }

    def __repr__(self):
        return f'<ShippingClass {self.name}>'
