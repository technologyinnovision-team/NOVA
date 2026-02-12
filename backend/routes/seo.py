from flask import Blueprint, make_response, request
from datetime import datetime
from xml.sax.saxutils import escape

from models import db
from models.product import Product, Category
from models.blog import BlogPost

seo_bp = Blueprint('seo', __name__)


@seo_bp.route('/sitemap.xml', methods=['GET'])
def sitemap():
    """Generate dynamic sitemap.xml for all important public pages."""

    # Base URL for frontend pages - derived from the actual request host
    base_url = request.url_root.rstrip('/')

    # Get current date for static pages
    current_date = datetime.utcnow().strftime('%Y-%m-%d')

    # 1. Static Pages (only real public, indexable pages)
    static_pages = [
        {'loc': f"{base_url}/", 'lastmod': current_date, 'changefreq': 'daily', 'priority': '1.0'},
        {'loc': f"{base_url}/products", 'lastmod': current_date, 'changefreq': 'daily', 'priority': '0.9'},
        {'loc': f"{base_url}/categories", 'lastmod': current_date, 'changefreq': 'weekly', 'priority': '0.8'},
        {'loc': f"{base_url}/perfumes", 'lastmod': current_date, 'changefreq': 'daily', 'priority': '0.9'},
        {'loc': f"{base_url}/contact", 'lastmod': current_date, 'changefreq': 'monthly', 'priority': '0.5'},
        {'loc': f"{base_url}/shipping", 'lastmod': current_date, 'changefreq': 'yearly', 'priority': '0.3'},
        {'loc': f"{base_url}/returns", 'lastmod': current_date, 'changefreq': 'yearly', 'priority': '0.3'},
        {'loc': f"{base_url}/faq", 'lastmod': current_date, 'changefreq': 'monthly', 'priority': '0.4'},
        {'loc': f"{base_url}/privacy", 'lastmod': current_date, 'changefreq': 'yearly', 'priority': '0.3'},
        {'loc': f"{base_url}/terms", 'lastmod': current_date, 'changefreq': 'yearly', 'priority': '0.3'},
        {'loc': f"{base_url}/blog", 'lastmod': current_date, 'changefreq': 'weekly', 'priority': '0.5'},
    ]

    # 2. Products (only published)
    products = Product.query.filter_by(status='published').all()
    product_urls = []
    for product in products:
        lastmod = product.updated_at.strftime('%Y-%m-%d') if product.updated_at else datetime.now().strftime('%Y-%m-%d')
        product_urls.append({
            'loc': f"{base_url}/products/{product.slug}",
            'lastmod': lastmod,
            'changefreq': 'weekly',
            'priority': '0.8'
        })

    # 3. Categories
    categories = Category.query.all()
    category_urls = []
    for category in categories:
        category_urls.append({
            'loc': f"{base_url}/categories/{category.slug}",
            'changefreq': 'weekly',
            'priority': '0.7'
        })
    # 4. Blog posts (only published & live)
    blog_posts = BlogPost.query.filter_by(status='published').all()
    blog_urls = []
    now_utc = datetime.utcnow()
    for post in blog_posts:
        # Respect publish date if set
        if not post.is_published:
            continue

        lastmod_dt = post.updated_at or post.published_at or now_utc
        lastmod = lastmod_dt.strftime('%Y-%m-%d')
        blog_urls.append({
            'loc': f"{base_url}/blog/{post.slug}",
            'lastmod': lastmod,
            'changefreq': 'weekly',
            'priority': '0.6'
        })

    # Generate XML
    xml = []
    xml.append('<?xml version="1.0" encoding="UTF-8"?>')
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    # Add Static Pages
    for page in static_pages:
        xml.append('  <url>')
        xml.append(f'    <loc>{escape(page["loc"])}</loc>')
        if 'lastmod' in page:
            xml.append(f'    <lastmod>{page["lastmod"]}</lastmod>')
        xml.append(f'    <changefreq>{page["changefreq"]}</changefreq>')
        xml.append(f'    <priority>{page["priority"]}</priority>')
        xml.append('  </url>')

    # Add Category Pages
    for page in category_urls:
        xml.append('  <url>')
        xml.append(f'    <loc>{escape(page["loc"])}</loc>')
        xml.append(f'    <changefreq>{page["changefreq"]}</changefreq>')
        xml.append(f'    <priority>{page["priority"]}</priority>')
        xml.append('  </url>')

    # Add Product Pages
    for page in product_urls:
        xml.append('  <url>')
        xml.append(f'    <loc>{escape(page["loc"])}</loc>')
        xml.append(f'    <lastmod>{page["lastmod"]}</lastmod>')
        xml.append(f'    <changefreq>{page["changefreq"]}</changefreq>')
        xml.append(f'    <priority>{page["priority"]}</priority>')
        xml.append('  </url>')

    # Add Blog Post Pages
    for page in blog_urls:
        xml.append('  <url>')
        xml.append(f'    <loc>{escape(page["loc"])}</loc>')
        xml.append(f'    <lastmod>{page["lastmod"]}</lastmod>')
        xml.append(f'    <changefreq>{page["changefreq"]}</changefreq>')
        xml.append(f'    <priority>{page["priority"]}</priority>')
        xml.append('  </url>')

    xml.append('</urlset>')
    
    response = make_response('\n'.join(xml))
    response.headers["Content-Type"] = "application/xml"
    return response

