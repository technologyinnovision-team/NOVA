import re
from werkzeug.utils import secure_filename
import unicodedata

def generate_slug(text):
    """Generate URL-friendly slug from text"""
    # Convert to lowercase
    text = text.lower()
    
    # Remove accents/diacritics
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    
    # Replace spaces and special chars with hyphens
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    
    # Remove leading/trailing hyphens
    text = text.strip('-')
    
    return text

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_price(price):
    """Validate price is positive number"""
    try:
        price_float = float(price)
        return price_float >= 0
    except (ValueError, TypeError):
        return False

def validate_stock(stock):
    """Validate stock quantity"""
    try:
        stock_int = int(stock)
        return stock_int >= 0
    except (ValueError, TypeError):
        return False

def validate_phone(phone):
    """Validate phone number format"""
    if not phone:
        return False
    # Basic phone validation - digits, spaces, dashes, parentheses, plus
    pattern = r'^[\d\s\-\+\(\)]{10,}$'
    return re.match(pattern, phone) is not None

def validate_required(data, fields):
    """Validate required fields in data dictionary"""
    missing = [field for field in fields if field not in data or data[field] is None or data[field] == '']
    return len(missing) == 0, missing

