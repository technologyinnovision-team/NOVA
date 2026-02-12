from datetime import datetime
from . import db

class Integration(db.Model):
    __tablename__ = 'integrations'
    
    id = db.Column(db.Integer, primary_key=True)
    integration_name = db.Column(db.String(50), unique=True, nullable=False)
    enabled = db.Column(db.Boolean, default=False, nullable=False)
    config = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Integration {self.integration_name}>'

