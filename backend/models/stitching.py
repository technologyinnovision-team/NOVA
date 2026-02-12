from datetime import datetime
from . import db

class StitchingService(db.Model):
    __tablename__ = 'stitching_services'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<StitchingService {self.name}>'

# Association Table for Product <-> StitchingService
product_stitching_services = db.Table('product_stitching_services',
    db.Column('product_id', db.Integer, db.ForeignKey('products.id'), primary_key=True),
    db.Column('stitching_service_id', db.Integer, db.ForeignKey('stitching_services.id'), primary_key=True)
)
