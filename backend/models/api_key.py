from datetime import datetime
import secrets
from . import db

class APIKey(db.Model):
    __tablename__ = 'api_keys'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    api_key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    api_secret_hash = db.Column(db.String(255), nullable=False)
    api_secret_plain = db.Column(db.Text, nullable=True)  # Only stored temporarily, should be shown once
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_used = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    description = db.Column(db.Text, nullable=True)
    
    created_by_user = db.relationship('User', backref='api_keys', lazy=True)
    
    def __repr__(self):
        return f'<APIKey {self.name}>'
    
    @staticmethod
    def generate_api_key():
        """Generate a unique API key"""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def generate_api_secret():
        """Generate a secure API secret"""
        return secrets.token_urlsafe(48)
    
    @staticmethod
    def hash_secret(secret):
        """Hash the API secret for storage"""
        from werkzeug.security import generate_password_hash
        return generate_password_hash(secret)
    
    def verify_secret(self, secret):
        """Verify API secret against hash"""
        from werkzeug.security import check_password_hash
        return check_password_hash(self.api_secret_hash, secret)
    
    def is_expired(self):
        """Check if API key has expired"""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at
