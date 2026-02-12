import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

load_dotenv()

class Config:
    """Base configuration class"""
    # Production: SECRET_KEY must be set via environment variable
    # Development: Falls back to dev key (only for local development)
    _secret_key = os.environ.get('SECRET_KEY')
    if not _secret_key:
        if os.environ.get('FLASK_ENV', 'development') == 'production':
            raise ValueError("SECRET_KEY environment variable must be set in production!")
        _secret_key = 'dev-secret-key-change-in-production'
    SECRET_KEY = _secret_key
    
    # Production Database Configuration
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = os.environ.get('DB_PORT', '3306')
    DB_USER = os.environ.get('DB_USER', 'bailebelle')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', 'bailebelle123@')
    DB_NAME = os.environ.get('DB_NAME', 'bailebelle')
    
    # URL-encode password to handle special characters like @, #, etc.
    encoded_password = quote_plus(DB_PASSWORD)
    SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{DB_USER}:{encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
        'pool_size': 10,
        'max_overflow': 20,
    }
    
    # Session Configuration
    SESSION_TYPE = 'sqlalchemy'
    SESSION_PERMANENT = False
    SESSION_USE_SIGNER = True
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour
    
    # File Upload Configuration
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max file size
    UPLOAD_FOLDER = 'uploads'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
    
    # Application Settings
    FLASK_ENV = os.environ.get('FLASK_ENV', 'development')
    # In production, DEBUG must be False
    DEBUG = os.environ.get('FLASK_DEBUG', 'False') == 'True' if FLASK_ENV == 'production' else os.environ.get('FLASK_DEBUG', 'True') == 'True'
    
    # API Configuration
    API_KEY = os.environ.get('API_KEY', 'ykf9E6S-xepvOUUx4a3ep3-jv-BsrRdzuS_rY5QXvHI')
    API_SECRET = os.environ.get('API_SECRET', 'FCNIq5etKSfor2QnnDm1aNpBX-gTBMHb4YKWoKezxumPIHeuKWBER1kvywLQxS1o')
    
    # Asset URL
    ASSET_URL = os.environ.get('ASSET_URL', 'http://localhost:8090')

    # Payment Gateways
    STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')

    # Hardcoded Configuration (Removed as per user request to use .env)
    # STRIPE_PUBLIC_KEY = 'pk_test_...'
    # STRIPE_SECRET_KEY = 'sk_test_...'
    # STRIPE_WEBHOOK_SECRET = 'whsec_...'
    
    PAYPAL_MODE = os.environ.get('PAYPAL_MODE', 'sandbox')
    PAYPAL_CLIENT_ID = os.environ.get('PAYPAL_CLIENT_ID')
    PAYPAL_CLIENT_SECRET = os.environ.get('PAYPAL_CLIENT_SECRET')

    # Update System Configuration
    GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
    REPO_OWNER = os.environ.get('REPO_OWNER')
    REPO_NAME = os.environ.get('REPO_NAME')
    # VERSION should be updated by the release process or read from a file
    VERSION = '1.0.0'

