from datetime import datetime
from . import db

class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False, index=True)
    product_type = db.Column(db.String(20), nullable=False, default='simple')  # simple, variable, external
    short_description = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    sku = db.Column(db.String(100), unique=True, nullable=True, index=True)
    gender = db.Column(db.JSON, nullable=True)  # ["men", "women", "kids"]
    
    # Pricing
    regular_price = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    sale_price = db.Column(db.Numeric(10, 2), nullable=True)
    wholesale_price = db.Column(db.Numeric(10, 2), nullable=True) # POS purchase price
    
    # Inventory
    stock_quantity = db.Column(db.Integer, default=0, nullable=False)
    manage_stock = db.Column(db.Boolean, default=False, nullable=False)
    stock_status = db.Column(db.String(20), default='in_stock', nullable=False)  # in_stock, out_of_stock, backorder
    
    # Physical Attributes
    weight = db.Column(db.Numeric(10, 2), nullable=True)
    length = db.Column(db.Numeric(10, 2), nullable=True)
    width = db.Column(db.Numeric(10, 2), nullable=True)
    height = db.Column(db.Numeric(10, 2), nullable=True)
    dimensions_unit = db.Column(db.String(10), default='cm', nullable=False)  # cm or in
    external_url = db.Column(db.Text, nullable=True)
    button_text = db.Column(db.String(100), nullable=True)
    
    # Status & Flags
    status = db.Column(db.String(20), default='draft', nullable=False)  # published, draft, private
    featured = db.Column(db.Boolean, default=False, nullable=False)
    on_sale = db.Column(db.Boolean, default=False, nullable=False)
    
    # Tax
    tax_status = db.Column(db.String(20), default='taxable', nullable=False)  # taxable, shipping, none
    tax_class = db.Column(db.String(50), nullable=True)  # Tax class identifier
    
    # Additional Inventory
    gtin = db.Column(db.String(50), nullable=True)  # GTIN/UPC/EAN/ISBN
    sold_individually = db.Column(db.Boolean, default=False, nullable=False)
    low_stock_threshold = db.Column(db.Integer, nullable=True)
    allow_backorders = db.Column(db.String(20), default='no', nullable=False)  # no, notify, yes
    
    # Shipping
    shipping_class_id = db.Column(db.Integer, db.ForeignKey('shipping_classes.id'), nullable=True)
    
    # Sizing
    # Field 'requires_sizing' removed
    # Field 'sizing_type' removed
    # Field 'sizing_options' removed
    
    # Advanced Payment Options
    # Field 'disable_cod' removed
    # Field 'payment_option' removed
    # Field 'advance_payment_amount' removed
    
    # Regional Availability
    available_countries = db.Column(db.JSON, nullable=True)  # List of country codes e.g. ["US", "GB", "PK"]
    
    # Custom Sizing Consultation
    # Custom Sizing Consultation
    # Field 'sizing_consultation_required' removed
    
    # Additional Fields
    purchase_note = db.Column(db.Text, nullable=True)
    allow_reviews = db.Column(db.Boolean, default=True, nullable=False)
    menu_order = db.Column(db.Integer, default=0, nullable=False)
    
    # Sale Price Date Range
    sale_price_start = db.Column(db.DateTime, nullable=True)
    sale_price_end = db.Column(db.DateTime, nullable=True)
    
    # SEO
    meta_title = db.Column(db.String(255), nullable=True)
    meta_description = db.Column(db.Text, nullable=True)
    meta_keywords = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    images = db.relationship('ProductImage', backref='product', lazy=True, cascade='all, delete-orphan', order_by='ProductImage.image_order')
    categories = db.relationship('Category', secondary='product_categories', lazy='subquery', backref=db.backref('products', lazy=True))
    tags = db.relationship('Tag', secondary='product_tags', lazy='subquery', backref=db.backref('products', lazy=True))
    attributes = db.relationship('ProductAttribute', backref='product', lazy=True, cascade='all, delete-orphan')
    variations = db.relationship('ProductVariation', backref='product', lazy=True, cascade='all, delete-orphan')
    shipping_class = db.relationship('ShippingClass', backref='products', lazy=True)
    
    # Linked Products - Many-to-many self-relationships
    upsells = db.relationship('Product', 
                             secondary='product_upsells',
                             primaryjoin='Product.id==product_upsells.c.product_id',
                             secondaryjoin='Product.id==product_upsells.c.upsell_id',
                             backref=db.backref('upselled_by', lazy='dynamic'),
                             lazy='subquery')
    
    cross_sells = db.relationship('Product',
                                  secondary='product_cross_sells',
                                  primaryjoin='Product.id==product_cross_sells.c.product_id',
                                  secondaryjoin='Product.id==product_cross_sells.c.cross_sell_id',
                                  backref=db.backref('cross_selled_by', lazy='dynamic'),
                                  lazy='subquery')

    # Stitching Services
    # Stitching Services - Removed
    
    def __repr__(self):
        return f'<Product {self.title}>'
    
    @property
    def primary_image(self):
        """Get the primary product image URL"""
        primary = next((img for img in self.images if img.is_primary), None)
        if primary:
            return primary.image_url
        elif self.images:
            return self.images[0].image_url
        return None

    def get_primary_image(self):
        """Get the primary ProductImage object"""
        return next((img for img in self.images if img.is_primary), None)

class ProductImage(db.Model):
    __tablename__ = 'product_images'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    image_url = db.Column(db.Text, nullable=False)
    image_order = db.Column(db.Integer, default=0, nullable=False)
    alt_text = db.Column(db.String(255), nullable=True)
    is_primary = db.Column(db.Boolean, default=False, nullable=False)
    
    def __repr__(self):
        return f'<ProductImage {self.id}>'

class Category(db.Model):
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    image_url = db.Column(db.Text, nullable=True)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    children = db.relationship('Category', backref=db.backref('parent', remote_side=[id]), lazy=True)
    
    def __repr__(self):
        return f'<Category {self.name}>'

# Association Tables
product_categories = db.Table('product_categories',
    db.Column('product_id', db.Integer, db.ForeignKey('products.id'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('categories.id'), primary_key=True)
)

class Tag(db.Model):
    __tablename__ = 'tags'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Tag {self.name}>'

product_tags = db.Table('product_tags',
    db.Column('product_id', db.Integer, db.ForeignKey('products.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id'), primary_key=True)
)

# Linked Products Association Tables
product_upsells = db.Table('product_upsells',
    db.Column('product_id', db.Integer, db.ForeignKey('products.id'), primary_key=True),
    db.Column('upsell_id', db.Integer, db.ForeignKey('products.id'), primary_key=True)
)

product_cross_sells = db.Table('product_cross_sells',
    db.Column('product_id', db.Integer, db.ForeignKey('products.id'), primary_key=True),
    db.Column('cross_sell_id', db.Integer, db.ForeignKey('products.id'), primary_key=True)
)

class ProductAttribute(db.Model):
    __tablename__ = 'product_attributes'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)  # e.g., "Color", "Size"
    type = db.Column(db.String(50), default='select', nullable=False)  # select, text, etc.
    visible = db.Column(db.Boolean, default=True, nullable=False)  # Visible on product page
    use_for_variations = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    terms = db.relationship('ProductAttributeTerm', backref='attribute', lazy=True, cascade='all, delete-orphan')
    __table_args__ = (
        db.UniqueConstraint('product_id', 'name', name='uq_product_attribute_name_per_product'),
    )
    
    def __repr__(self):
        return f'<ProductAttribute {self.name}>'

class ProductAttributeTerm(db.Model):
    __tablename__ = 'product_attribute_terms'
    
    id = db.Column(db.Integer, primary_key=True)
    attribute_id = db.Column(db.Integer, db.ForeignKey('product_attributes.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)  # e.g., "Red", "Large"
    slug = db.Column(db.String(100), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('attribute_id', 'slug', name='uq_attribute_term_slug_per_attribute'),
    )
    
    def __repr__(self):
        return f'<ProductAttributeTerm {self.name}>'

class ProductVariation(db.Model):
    __tablename__ = 'product_variations'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    sku = db.Column(db.String(100), unique=True, nullable=True, index=True)
    regular_price = db.Column(db.Numeric(10, 2), nullable=True)
    sale_price = db.Column(db.Numeric(10, 2), nullable=True)
    wholesale_price = db.Column(db.Numeric(10, 2), nullable=True)
    manage_stock = db.Column(db.Boolean, default=False, nullable=False)
    stock_quantity = db.Column(db.Integer, default=0, nullable=False)
    stock_status = db.Column(db.String(20), default='in_stock', nullable=False)
    weight = db.Column(db.Numeric(10, 2), nullable=True)
    length = db.Column(db.Numeric(10, 2), nullable=True)
    width = db.Column(db.Numeric(10, 2), nullable=True)
    height = db.Column(db.Numeric(10, 2), nullable=True)
    dimensions_unit = db.Column(db.String(10), default='cm', nullable=False)
    image_url = db.Column(db.Text, nullable=True)
    attribute_terms = db.Column(db.JSON, nullable=False)  # {"Color": "Red", "Size": "Large"}
    status = db.Column(db.String(20), default='publish', nullable=False)  # publish, private
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ProductVariation {self.id}>'

