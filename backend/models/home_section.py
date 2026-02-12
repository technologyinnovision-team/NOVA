from . import db
from datetime import datetime

class HomeSection(db.Model):
    __tablename__ = 'home_sections'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    subtitle = db.Column(db.String(255), nullable=True)
    
    # Section Type: 'category', 'featured', 'sale', 'new_arrivals', 'best_selling'
    section_type = db.Column(db.String(50), nullable=False, default='category')
    
    # For 'category' type
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    
    item_limit = db.Column(db.Integer, default=12, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    category = db.relationship('Category', backref='home_sections', lazy=True)
    
    def __repr__(self):
        return f'<HomeSection {self.title}>'
