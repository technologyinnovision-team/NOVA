from datetime import datetime
from . import db

class Setting(db.Model):
    """Application settings stored in database"""
    __tablename__ = 'settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)
    value_type = db.Column(db.String(20), default='string', nullable=False)  # string, json, number, boolean
    category = db.Column(db.String(50), nullable=False, index=True)  # tax, smtp, admin_emails
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Setting {self.key}>'
    
    @staticmethod
    def get(key, default=None):
        """Get setting value by key"""
        setting = Setting.query.filter_by(key=key).first()
        if not setting:
            return default
        
        if setting.value_type == 'json':
            import json
            try:
                return json.loads(setting.value) if setting.value else default
            except:
                return default
        elif setting.value_type == 'number':
            try:
                return float(setting.value) if setting.value else default
            except:
                return default
        elif setting.value_type == 'boolean':
            return setting.value.lower() in ('true', '1', 'yes', 'on') if setting.value else default
        else:
            return setting.value if setting.value else default
    
    @staticmethod
    def set(key, value, value_type='string', category='general', description=None):
        """Set setting value by key"""
        setting = Setting.query.filter_by(key=key).first()
        
        if setting:
            if value_type == 'json':
                import json
                setting.value = json.dumps(value) if value is not None else None
            else:
                setting.value = str(value) if value is not None else None
            setting.value_type = value_type
            setting.category = category
            if description:
                setting.description = description
            setting.updated_at = datetime.utcnow()
        else:
            if value_type == 'json':
                import json
                value_str = json.dumps(value) if value is not None else None
            else:
                value_str = str(value) if value is not None else None
            
            setting = Setting(
                key=key,
                value=value_str,
                value_type=value_type,
                category=category,
                description=description
            )
            db.session.add(setting)
        
        db.session.commit()
        return setting

