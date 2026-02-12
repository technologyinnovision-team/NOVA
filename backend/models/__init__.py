from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from .user import User, Role
from .product import Product, ProductImage, Category, Tag, ProductAttribute, ProductAttributeTerm, ProductVariation
from .customer import Customer
from .order import Order, OrderItem
from .pos import POSSellerProfile, POSInventory
from .shipping import ShippingZone, ShippingZoneLocation, ShippingClass, ShippingMethod

from .payment import PaymentGateway
from .integration import Integration
from .api_key import APIKey
from .blog import BlogPost, BlogCategory, BlogTag
from .setting import Setting
from .coupon import Coupon
from .deal import Deal, DealSlot, deal_slot_categories, deal_slot_products
from .home_section import HomeSection
from .wallet import Wallet, WalletTransaction, PayoutRequest

__all__ = [
    'db',
    'User', 'Role',
    'Product', 'ProductImage', 'Category', 'Tag',
    'ProductAttribute', 'ProductAttributeTerm', 'ProductVariation',
    'Customer',
    'Order', 'OrderItem',
    'POSSellerProfile', 'POSInventory',
    'ShippingZone', 'ShippingZoneLocation', 'ShippingClass', 'ShippingMethod',
    'PaymentGateway',
    'Integration',
    'APIKey',
    'BlogPost', 'BlogCategory', 'BlogTag',
    'Setting',
    'Coupon',
    'Deal', 'DealSlot',
    'HomeSection',
    'Wallet', 'WalletTransaction', 'PayoutRequest'
]

