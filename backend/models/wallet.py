from datetime import datetime
from . import db

class Wallet(db.Model):
    __tablename__ = 'wallets'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    balance = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    currency = db.Column(db.String(3), default='USD', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to user is defined in User model (backref)
    transactions = db.relationship('WalletTransaction', backref='wallet', lazy='dynamic', order_by='desc(WalletTransaction.created_at)')
    payout_requests = db.relationship('PayoutRequest', backref='wallet', lazy='dynamic', order_by='desc(PayoutRequest.created_at)')

    def __repr__(self):
        return f'<Wallet User:{self.user_id} Balance:{self.balance}>'

class WalletTransaction(db.Model):
    __tablename__ = 'wallet_transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    wallet_id = db.Column(db.Integer, db.ForeignKey('wallets.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    balance_after = db.Column(db.Numeric(10, 2), nullable=False)
    type = db.Column(db.String(20), nullable=False) # CREDIT, DEBIT, PAYOUT
    status = db.Column(db.String(20), default='completed', nullable=False) # completed, pending, failed
    reference_id = db.Column(db.String(255), nullable=True) # Order ID, Payment Intent ID, etc.
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<WalletTransaction {self.type} {self.amount}>'

class PayoutRequest(db.Model):
    __tablename__ = 'payout_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    wallet_id = db.Column(db.Integer, db.ForeignKey('wallets.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    paypal_email = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False) # pending, processing, completed, failed, cancelled
    batch_id = db.Column(db.String(255), nullable=True) # PayPal Payout Batch ID
    admin_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f'<PayoutRequest {self.id} {self.status}>'
