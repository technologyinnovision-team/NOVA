from datetime import datetime
from . import db

class Role(db.Model):
    __tablename__ = 'roles'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    permissions = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    users = db.relationship('User', backref='role', lazy=True)

    # Role Constants
    ADMIN = 'Admin'
    POS_SELLER = 'POS Seller'
    CUSTOMER = 'Customer'
    
    def __repr__(self):
        return f'<Role {self.name}>'

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    def check_permission(self, permission):
        """Check if user has a specific permission"""
        if not self.role:
            return False
        return self.role.permissions.get(permission, False) if isinstance(self.role.permissions, dict) else False

    # Wallet Relationship
    wallet = db.relationship('Wallet', backref='user', uselist=False, cascade='all, delete-orphan')

