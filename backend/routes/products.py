from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from models import db
from models.product import Product, ProductImage, Category, Tag, ProductAttribute, ProductAttributeTerm, ProductVariation
from models.shipping import ShippingClass
from models.stitching import StitchingService
from utils.permissions import login_required
from utils.upload import upload_file_local, delete_file_local, allowed_file, download_file_from_url
from utils.validators import generate_slug, validate_price, validate_stock
from werkzeug.utils import secure_filename
from decimal import Decimal
from datetime import datetime
from itertools import product as itertools_product
import json
from utils.woocommerce_csv_import import parse_woocommerce_csv

products = Blueprint('products', __name__, url_prefix='/admin/products')

@products.route('/')
@login_required
def list():
    """Product listing page with advanced filtering"""
    from sqlalchemy import or_, and_
    
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '')
    category_filter = request.args.get('category', '')
    category_slug_filter = request.args.get('category_slug', '')
    product_type_filter = request.args.get('product_type', '')
    stock_status_filter = request.args.get('stock_status', '')
    featured_filter = request.args.get('featured', '')
    on_sale_filter = request.args.get('on_sale', '')
    
    query = Product.query
    
    # Search filter
    if search:
        query = query.filter(
            or_(
                Product.title.ilike(f'%{search}%'),
                Product.sku.ilike(f'%{search}%'),
                Product.short_description.ilike(f'%{search}%')
            )
        )
    
    # Status filter
    if status_filter:
        query = query.filter(Product.status == status_filter)
    
    # Category filter (ID)
    if category_filter:
        try:
            category_id = int(category_filter)
            query = query.join(Product.categories).filter(Category.id == category_id)
        except:
            pass
            
    # Category filter (Slug)
    if category_slug_filter:
        # Check if we already joined categories (avoid double join error if both filters present)
        if not category_filter:
            query = query.join(Product.categories)
        query = query.filter(Category.slug == category_slug_filter)
    
    # Product type filter
    if product_type_filter:
        query = query.filter(Product.product_type == product_type_filter)
    
    # Stock status filter
    if stock_status_filter:
        query = query.filter(Product.stock_status == stock_status_filter)
    
    # Featured filter
    if featured_filter == 'yes':
        query = query.filter(Product.featured == True)
    elif featured_filter == 'no':
        query = query.filter(Product.featured == False)
    
    # On sale filter
    if on_sale_filter == 'yes':
        query = query.filter(Product.on_sale == True)
    elif on_sale_filter == 'no':
        query = query.filter(Product.on_sale == False)
    
    # Get counts for filter badges
    total_count = Product.query.count()
    published_count = Product.query.filter_by(status='published').count()
    draft_count = Product.query.filter_by(status='draft').count()
    private_count = Product.query.filter_by(status='private').count()
    
    products_paginated = query.order_by(Product.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Calculate price ranges for variable products
    products_with_prices = []
    for product in products_paginated.items:
        price_info = {'product': product, 'is_variable': False, 'price_range': None}
        
        if product.product_type == 'variable':
            # Get variation prices
            variations = ProductVariation.query.filter_by(product_id=product.id).all()
            if variations:
                prices = []
                for var in variations:
                    # Use sale price if available, otherwise regular price
                    price = var.sale_price if var.sale_price else var.regular_price
                    if price and price > 0:
                        prices.append(float(price))
                
                if prices:
                    min_price = min(prices)
                    max_price = max(prices)
                    if min_price == max_price:
                        price_info['price_range'] = f"${min_price:.2f}"
                    else:
                        price_info['price_range'] = f"${min_price:.2f} - ${max_price:.2f}"
                price_info['is_variable'] = True
        
        products_with_prices.append(price_info)
    
    # Get all categories for filter dropdown
    all_categories = Category.query.order_by(Category.name).all()
    
    return render_template('products/list.html', 
                         products_with_prices=products_with_prices,
                         pagination=products_paginated,
                         search=search,
                         status_filter=status_filter,
                         category_filter=category_filter,
                         product_type_filter=product_type_filter,
                         stock_status_filter=stock_status_filter,
                         featured_filter=featured_filter,
                         on_sale_filter=on_sale_filter,
                         categories=all_categories,
                         total_count=total_count,
                         published_count=published_count,
                         draft_count=draft_count,
                         private_count=private_count)


@products.route('/stocks')
@login_required
def stocks():
    """Stock Management Page"""
    from sqlalchemy import or_
    
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    stock_status_filter = request.args.get('stock_status', '')
    
    query = Product.query
    
    if search:
        query = query.filter(
            or_(
                Product.title.ilike(f'%{search}%'),
                Product.sku.ilike(f'%{search}%')
            )
        )
    
    if stock_status_filter:
        query = query.filter(Product.stock_status == stock_status_filter)
        
    products_paginated = query.order_by(Product.title.asc()).paginate(
        page=page, per_page=50, error_out=False
    )
    
    return render_template('products/stocks.html', 
                         pagination=products_paginated,
                         search=search,
                         stock_status_filter=stock_status_filter)

@login_required
def quick_edit(id):
    """Handle Quick Edit AJAX request"""
    try:
        product = Product.query.get_or_404(id)
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        # Update fields
        if 'title' in data:
            product.title = data['title'].strip()
            
        if 'slug' in data:
            new_slug = data['slug'].strip()
            if new_slug and new_slug != product.slug:
                # Check uniqueness excluding self
                if Product.query.filter(Product.slug == new_slug, Product.id != product.id).first():
                    return jsonify({'success': False, 'message': f'Slug "{new_slug}" already exists'}), 400
                product.slug = new_slug
                
        if 'status' in data:
            if data['status'] in ['published', 'draft', 'private', 'coming_soon']:
                product.status = data['status']

        if 'sku' in data:
            new_sku = data['sku'].strip() or None
            if new_sku != product.sku:
                # Check uniqueness
                if new_sku and Product.query.filter(Product.sku == new_sku, Product.id != product.id).first():
                    return jsonify({'success': False, 'message': f'SKU "{new_sku}" already exists'}), 400
                product.sku = new_sku
                
        if 'regular_price' in data:
            try:
                product.regular_price = Decimal(data['regular_price'])
            except:
                return jsonify({'success': False, 'message': 'Invalid regular price format'}), 400
                
        if 'sale_price' in data:
            try:
                sale_price = data['sale_price']
                if sale_price and str(sale_price).strip():
                    product.sale_price = Decimal(sale_price)
                else:
                    product.sale_price = None
                
                # Auto-update on_sale status
                product.on_sale = product.sale_price is not None and product.sale_price > 0
            except:
                return jsonify({'success': False, 'message': 'Invalid sale price format'}), 400
                
        if 'stock_quantity' in data:
            try:
                product.stock_quantity = int(data['stock_quantity'])
            except:
                pass
                
        if 'manage_stock' in data:
            product.manage_stock = bool(data['manage_stock'])
        
        # Update Categories
        if 'categories' in data:
            category_ids = data['categories']
            product.categories.clear()
            for cat_id in category_ids:
                category = Category.query.get(int(cat_id))
                if category:
                    product.categories.append(category)
        
        db.session.commit()
        
        # Determine price info for template
        price_info = {'product': product, 'is_variable': False, 'price_range': None}
        if product.product_type == 'variable':
             # Re-calculate variations (simplified for quick edit context, assuming variations didn't change price here)
             # But let's copy logic from list() to be safe or just mark as variable
             # For a robust implementation, we should re-query variations
             variations = ProductVariation.query.filter_by(product_id=product.id).all()
             if variations:
                prices = []
                for var in variations:
                    price = var.sale_price if var.sale_price else var.regular_price
                    if price and price > 0:
                        prices.append(float(price))
                if prices:
                    min_price = min(prices)
                    max_price = max(prices)
                    if min_price == max_price:
                        price_info['price_range'] = f"${min_price:.2f}"
                    else:
                        price_info['price_range'] = f"${min_price:.2f} - ${max_price:.2f}"
                price_info['is_variable'] = True
        
        # Render the row partial
        row_html = render_template('products/partials/product_row.html', item=price_info)
        
        return jsonify({
            'success': True,
            'row_html': row_html
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Quick Edit Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@products.route('/generate-ai-content', methods=['POST'])
@login_required
def generate_ai_content():
    """Generate product content using AI (Groq/Llama Vision)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        series_name = data.get('series_name', '')
        user_prompt = data.get('prompt', '')
        options = data.get('options', [])
        image_urls = data.get('images', [])

        if not image_urls:
            return jsonify({'error': 'No images provided'}), 400

        # Construct the detailed system prompt based on options
        system_instruction = """You are an expert e-commerce content creator and SEO specialist. 
        Analyze the provided product images and generate detailed, premium, and sales-driven content.
        
        You must strictly output ONLY valid JSON format. Do not include markdown formatting like ```json ... ```.
        
        The JSON structure should be:
        {
            "title": "Compelling Product Title",
            "short_description": "2-3 sentences summary",
            "description": "HTML formatted long description with features, styling tips, and material info. Use <h3>, <p>, <ul>, <li> tags.",
            "price": 0.00,
            "meta_title": "SEO optimized title (max 60 chars)",
            "meta_description": "SEO optimized description (max 160 chars)"
        }
        
        Generate only the fields that are requested based on the input options, but keeping the JSON structure valid is key.
        Prices should be estimated based on the luxuriousness of the item (in USD or the implied currency).
        """

        user_content = []
        
        # 1. Text Instruction
        instruction_text = f"Analyze these images. Series/Reference Name: {series_name}. \nUser Instructions: {user_prompt}\n"
        if options:
            instruction_text += f"Please generate the following fields: {', '.join(options)}."
        
        user_content.append({"type": "text", "text": instruction_text})

        # 2. Images
        # Limit to first 3 images to avoid token limits/latency if necessary, or send all if supported.
        # Groq's Llama vision models support multiple images.
        import base64
        import os
        from flask import current_app

        for url in image_urls[:4]: 
            # Check if it's a data URL or http URL
            image_payload = {}
            
            if url.startswith('data:image'):
                 image_payload = {"url": url}
            elif url.startswith('/uploads/'):
                # Local file - convert to base64
                try:
                    # Remove leading slash and join with root path
                    # Assuming url is like /uploads/products/image.jpg
                    # and static/uploads mapping might be involved, but typically here it's relative to root or static
                    
                    # We need to find the real path. 
                    # If config says UPLOAD_FOLDER = 'uploads', and it's in root.
                    file_path = os.path.join(current_app.root_path, url.lstrip('/'))
                    # If the app structure is root/uploads vs root/backend/uploads...
                    # Current cwd is Backend, app.root_path should be Backend.
                    
                    if not os.path.exists(file_path):
                         # Try 'static' prefix just in case or bare uploads
                         file_path = os.path.join(current_app.root_path, 'uploads', url.replace('/uploads/', ''))
                    
                    if os.path.exists(file_path):
                        with open(file_path, "rb") as image_file:
                            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                            # Determine mime type
                            ext = url.split('.')[-1].lower()
                            mime = 'jpeg' if ext == 'jpg' else ext
                            if mime == 'svg': mime = 'svg+xml'
                            
                            image_payload = {"url": f"data:image/{mime};base64,{base64_image}"}
                    else:
                        print(f"File not found for AI gen: {file_path}")
                        continue
                except Exception as e:
                    print(f"Error converting image to base64: {e}")
                    continue
            elif url.startswith('http'):
                 image_payload = {"url": url}
            else:
                continue

            if image_payload:
                user_content.append({
                    "type": "image_url",
                    "image_url": image_payload
                })

        # Initialize Client
        # Using the hardcoded key as requested by the user
        from openai import OpenAI
        client = OpenAI(
            api_key=os.environ.get('GROQ_API_KEY', 'your-groq-api-key'),
            base_url="https://api.groq.com/openai/v1",
        )

        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct", # Using the model specified by user
            messages=[
                {
                    "role": "system",
                    "content": system_instruction
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ],
            temperature=0.4, # Lower temperature for more consistent JSON
            max_tokens=2048,
            top_p=1,
            stream=False,
            response_format={"type": "json_object"} # Enforce JSON mode if supported
        )

        content = response.choices[0].message.content
        
        # Clean up if markdown code blocks are present despite instructions
        if "```json" in content:
            content = content.replace("```json", "").replace("```", "")
        elif "```" in content:
            content = content.replace("```", "")
            
        return content, 200, {'Content-Type': 'application/json'}

    except Exception as e:
        print(f"AI Generation Error: {str(e)}")
        # In production log the full traceback
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@products.route('/create', methods=['GET', 'POST'])

@login_required
def create():
    """Create product page"""
    if request.method == 'POST':
        try:
            # Basic fields
            title = request.form.get('title', '').strip()
            if not title:
                flash('Product title is required.', 'error')
                return render_template('products/create_edit.html', 
                                     categories=get_all_categories(),
                                     tags=get_all_tags(),
                                     shipping_classes=ShippingClass.query.order_by(ShippingClass.name).all(),
                                     all_products=Product.query.filter(Product.status == 'published').order_by(Product.title).all(),
                                     form_data=request.form)
            
            slug = request.form.get('slug', '').strip() or generate_slug(title)
            
            # Check if slug exists
            if Product.query.filter_by(slug=slug).first():
                slug = f"{slug}-{int(datetime.now().timestamp())}"
            
            product_type = request.form.get('product_type', 'simple')
            
            # Validate SKU uniqueness
            sku = request.form.get('sku', '').strip()
            if not sku or sku == 'None':
                sku = None
            
            if sku and Product.query.filter_by(sku=sku).first():
                flash(f'SKU "{sku}" already exists. Please use a unique SKU.', 'error')
                return render_template('products/create_edit.html', 
                                     categories=get_all_categories(),
                                     tags=get_all_tags(),
                                     shipping_classes=ShippingClass.query.order_by(ShippingClass.name).all(),
                                     all_products=Product.query.filter(Product.status == 'published').order_by(Product.title).all(),
                                     form_data=request.form)
            
            # For variable products, pricing and stock are managed at variation level
            # Set defaults for variable products
            if product_type == 'variable':
                regular_price = Decimal(0)
                sale_price = None
                stock_quantity = 0
                manage_stock = False
            else:
                regular_price = Decimal(request.form.get('regular_price', 0) or 0)
                sale_price = Decimal(request.form.get('sale_price', 0) or 0) if request.form.get('sale_price') else None
                wholesale_price = Decimal(request.form.get('wholesale_price', 0) or 0) if request.form.get('wholesale_price') else None
                stock_quantity = int(request.form.get('stock_quantity', 0) or 0)
                manage_stock = request.form.get('manage_stock') == 'on'
            
            # Parse sale price date range
            sale_start = None
            sale_end = None
            if request.form.get('sale_price_start'):
                try:
                    sale_start = datetime.strptime(request.form.get('sale_price_start'), '%Y-%m-%d')
                except:
                    pass
            if request.form.get('sale_price_end'):
                try:
                    sale_end = datetime.strptime(request.form.get('sale_price_end'), '%Y-%m-%d')
                except:
                    pass
            
            # Get shipping class
            shipping_class_id = None
            if request.form.get('shipping_class'):
                try:
                    shipping_class_id = int(request.form.get('shipping_class'))
                except:
                    pass
            
            product = Product(
            title=title,
            slug=slug,
            product_type=product_type,
            short_description=request.form.get('short_description', ''),
            # Get description - it comes from Quill as HTML, so keep it as-is
            description=request.form.get('description', '').strip(),
            sku=sku,
            regular_price=regular_price,
            sale_price=sale_price,
            wholesale_price=wholesale_price,
            sale_price_start=sale_start,
            sale_price_end=sale_end,
            tax_status=request.form.get('tax_status', 'taxable'),
            tax_class=request.form.get('tax_class', '').strip() or None,
            gtin=request.form.get('gtin', '').strip() or None,
            stock_quantity=stock_quantity,
            manage_stock=manage_stock,
            stock_status=request.form.get('stock_status', 'in_stock'),
            low_stock_threshold=int(request.form.get('low_stock_threshold', 0) or 0) if request.form.get('low_stock_threshold') else None,
            allow_backorders=request.form.get('allow_backorders', 'no'),
            sold_individually=request.form.get('sold_individually') == 'on',
            weight=Decimal(request.form.get('weight', 0) or 0) if request.form.get('weight') else None,
            length=Decimal(request.form.get('length', 0) or 0) if request.form.get('length') else None,
            width=Decimal(request.form.get('width', 0) or 0) if request.form.get('width') else None,
            height=Decimal(request.form.get('height', 0) or 0) if request.form.get('height') else None,
            dimensions_unit=request.form.get('dimensions_unit', 'cm'),
            shipping_class_id=shipping_class_id,
            requires_sizing=request.form.get('requires_sizing') == 'on',
            sizing_type=request.form.get('sizing_type', '').strip() or None if request.form.get('requires_sizing') == 'on' else None,
            sizing_options=json.loads(request.form.get('sizing_options', '[]')) if request.form.get('requires_sizing') == 'on' and request.form.get('sizing_options') else None,
            disable_cod=request.form.get('disable_cod') == 'on',
            payment_option=request.form.get('payment_option', 'cod_available'),
            advance_payment_amount=Decimal(request.form.get('advance_payment_amount', 0) or 0) if request.form.get('payment_option') == 'partial_advance' else None,
            sizing_consultation_required=request.form.get('sizing_consultation_required') == 'on',
            purchase_note=request.form.get('purchase_note', '').strip() or None,
            allow_reviews=request.form.get('allow_reviews', 'on') == 'on',
            menu_order=int(request.form.get('menu_order', 0) or 0),
            status=request.form.get('status', 'draft'),
            featured=request.form.get('featured') == 'on',
            on_sale=(sale_price is not None and sale_price > 0),
            external_url=request.form.get('external_url', '').strip() or None if product_type == 'external' else None,
            button_text=request.form.get('button_text', '').strip() or None if product_type == 'external' else None,
            meta_title=request.form.get('meta_title', '').strip() or None,
            meta_description=request.form.get('meta_description', '').strip() or None,
            meta_keywords=request.form.get('meta_keywords', '').strip() or None,
            available_countries=json.loads(request.form.get('available_countries', '[]')) if request.form.get('available_countries') else None,
            gender=request.form.getlist('gender') if request.form.getlist('gender') else None,
            )
            
            db.session.add(product)
            db.session.flush()  # Get product ID
            
            # Handle categories
            category_ids = request.form.getlist('categories')
            for category_id in category_ids:
                category = Category.query.get(int(category_id))
                if category:
                    product.categories.append(category)
            
            # Handle tags - split comma-separated string
            tags_input = request.form.get('tags', '').strip()
            if tags_input:
                tag_names = [t.strip() for t in tags_input.split(',') if t.strip()]
                for tag_name in tag_names:
                    tag = Tag.query.filter_by(name=tag_name).first()
                    if not tag:
                        tag = Tag(name=tag_name, slug=generate_slug(tag_name))
                        db.session.add(tag)
                    if tag not in product.tags:
                        product.tags.append(tag)
            
            # Handle images from Media Gallery Modal
            new_media_urls_json = request.form.get('new_media_urls', '[]')
            primary_identifier = request.form.get('primary_image_identifier', '')
            
            try:
                new_media_urls = json.loads(new_media_urls_json)
            except:
                new_media_urls = []

            # Current max order
            image_order = 0
            primary_set = False

            # 1. Process New Media URLs (from Library)
            for url in new_media_urls:
                if url:
                    # Check if this specific URL is marked as primary
                    is_primary = (url == primary_identifier)
                    if is_primary: primary_set = True
                    
                    product_image = ProductImage(
                        product_id=product.id,
                        image_url=url,
                        image_order=image_order,
                        alt_text='',
                        is_primary=is_primary
                    )
                    db.session.add(product_image)
                    image_order += 1
            
            # 2. Uploads (Legacy/Direct) - Kept as fallback or for other forms
            image_files = request.files.getlist('images')
            for image_file in image_files:
                if image_file and image_file.filename and allowed_file(image_file.filename):
                    try:
                        image_url = upload_file_local(image_file, folder='products')
                        is_primary = not primary_set # if no primary yet, this is it
                        if is_primary: primary_set = True
                        
                        product_image = ProductImage(
                            product_id=product.id,
                            image_url=image_url,
                            image_order=image_order,
                            alt_text='',
                            is_primary=is_primary
                        )
                        db.session.add(product_image)
                        image_order += 1
                    except Exception as e:
                        print(f"Error uploading image: {e}")
            
            # 3. External URLs (Legacy)
            image_urls = request.form.getlist('image_urls')
            for url in image_urls:
                if url and url.strip():
                    is_primary = not primary_set
                    if is_primary: primary_set = True
                    
                    product_image = ProductImage(
                        product_id=product.id,
                        image_url=url.strip(),
                        image_order=image_order,
                        alt_text='',
                        is_primary=is_primary
                    )
                    db.session.add(product_image)
                    image_order += 1

            
            # Handle attributes
            if product_type == 'variable':
                attr_names = request.form.getlist('attr_name[]')
                attr_values = request.form.getlist('attr_values[]')
                # Use hidden inputs to track checkbox states (always submitted regardless of checked state)
                attr_visible_idx = request.form.getlist('attr_visible_idx[]')
                attr_use_for_variations_idx = request.form.getlist('attr_use_for_variations_idx[]')
                
                for idx, attr_name in enumerate(attr_names):
                    if attr_name and attr_name.strip():
                        # Check if checkbox was checked by checking the hidden input value
                        visible = idx < len(attr_visible_idx) and attr_visible_idx[idx] == '1'
                        use_for_variations = idx < len(attr_use_for_variations_idx) and attr_use_for_variations_idx[idx] == '1'
                        
                        attr = ProductAttribute(
                            product_id=product.id,
                            name=attr_name.strip(),
                            visible=visible,
                            use_for_variations=use_for_variations
                        )
                        db.session.add(attr)
                        db.session.flush()
                        
                        # Add terms
                        if idx < len(attr_values) and attr_values[idx]:
                            term_names = [t.strip() for t in attr_values[idx].split(',') if t.strip()]
                            for term_name in term_names:
                                term_slug = generate_slug(term_name)
                                term = ProductAttributeTerm(
                                    attribute_id=attr.id,
                                    name=term_name,
                                    slug=term_slug
                                )
                                db.session.add(term)
            
            # Handle variations
            if product_type == 'variable':
                variation_attrs = request.form.getlist('variation_attributes[]')
                variation_skus = request.form.getlist('variation_sku[]')
                variation_regular_prices = request.form.getlist('variation_regular_price[]')
                variation_sale_prices = request.form.getlist('variation_sale_price[]')
                variation_wholesale_prices = request.form.getlist('variation_wholesale_price[]')
                variation_stocks = request.form.getlist('variation_stock[]')
                variation_images = request.form.getlist('variation_images[]')
                
                for idx, var_attrs in enumerate(variation_attrs):
                    if not var_attrs.strip():
                        continue
                    
                    # Parse attributes (format: "Color: Red | Size: M")
                    attr_dict = {}
                    for pair in var_attrs.split('|'):
                        if ':' in pair:
                            key, val = pair.split(':', 1)
                            attr_dict[key.strip()] = val.strip()
                    
                    var_sku = variation_skus[idx] if idx < len(variation_skus) else None
                    if var_sku:
                        # Check SKU uniqueness
                        if ProductVariation.query.filter_by(sku=var_sku).first():
                            var_sku = f"{var_sku}-{product.id}-{idx}"
                    
                    variation = ProductVariation(
                        product_id=product.id,
                        sku=var_sku.strip() if var_sku else None,
                        regular_price=Decimal(variation_regular_prices[idx] or 0) if idx < len(variation_regular_prices) and variation_regular_prices[idx] else None,
                        sale_price=Decimal(variation_sale_prices[idx] or 0) if idx < len(variation_sale_prices) and variation_sale_prices[idx] else None,
                        wholesale_price=Decimal(variation_wholesale_prices[idx] or 0) if idx < len(variation_wholesale_prices) and variation_wholesale_prices[idx] else None,
                        stock_quantity=int(variation_stocks[idx] or 0) if idx < len(variation_stocks) else 0,
                        manage_stock=True if idx < len(variation_stocks) and variation_stocks[idx] else False,
                        attribute_terms=attr_dict,
                        image_url=variation_images[idx].strip() if idx < len(variation_images) and variation_images[idx] else None,
                        status='publish'
                    )
                    db.session.add(variation)
            
            # Handle upsells and cross-sells
            upsell_ids = request.form.getlist('upsells')
            for upsell_id in upsell_ids:
                try:
                    upsell_product = Product.query.get(int(upsell_id))
                    if upsell_product and upsell_product.id != product.id:
                        product.upsells.append(upsell_product)
                except:
                    pass
            
            cross_sell_ids = request.form.getlist('cross_sells')
            for cross_sell_id in cross_sell_ids:
                try:
                    cross_sell_product = Product.query.get(int(cross_sell_id))
                    if cross_sell_product and cross_sell_product.id != product.id:
                        product.cross_sells.append(cross_sell_product)
                except:
                    pass
            


            db.session.commit()
            
            flash('Product created successfully!', 'success')
            return redirect(url_for('products.edit', id=product.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating product: {str(e)}', 'error')
            print(f"Error: {e}")
    
    shipping_classes = ShippingClass.query.order_by(ShippingClass.name).all()
    all_products = Product.query.filter(Product.status == 'published').order_by(Product.title).all()

    return render_template('products/create_edit.html',
                         categories=get_all_categories(),
                         tags=get_all_tags(),
                         shipping_classes=shipping_classes,
                         all_products=all_products,
                        )

@products.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Edit product page"""
    product = Product.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            if not title:
                flash('Product title is required.', 'error')
                return render_template('products/create_edit.html',
                                     product=product,
                                     categories=get_all_categories(),
                                     tags=get_all_tags(),
                                     shipping_classes=ShippingClass.query.order_by(ShippingClass.name).all(),
                                     all_products=Product.query.filter(Product.status == 'published').order_by(Product.title).all())
            
            slug = request.form.get('slug', '').strip() or generate_slug(title)
            if slug != product.slug and Product.query.filter_by(slug=slug).first():
                slug = f"{slug}-{int(datetime.now().timestamp())}"
            
            product.title = title
            product.slug = slug
            product.short_description = request.form.get('short_description', '')
            # Get description - it comes from Quill as HTML, so keep it as-is
            product.description = request.form.get('description', '').strip()
            
            sku = request.form.get('sku', '').strip()
            if not sku or sku == 'None':
                sku = None
            product.sku = sku
            product.product_type = request.form.get('product_type', 'simple')
            product.external_url = request.form.get('external_url', '').strip() or None if product.product_type == 'external' else None
            product.button_text = request.form.get('button_text', '').strip() or None if product.product_type == 'external' else None
            
            if product.product_type == 'variable':
                product.regular_price = Decimal(0)
                product.sale_price = None
                product.wholesale_price = None
                product.stock_quantity = 0
                product.manage_stock = False
            else:
                product.regular_price = Decimal(request.form.get('regular_price', 0) or 0)
                product.sale_price = Decimal(request.form.get('sale_price', 0) or 0) if request.form.get('sale_price') else None
                product.wholesale_price = Decimal(request.form.get('wholesale_price', 0) or 0) if request.form.get('wholesale_price') else None
                product.stock_quantity = int(request.form.get('stock_quantity', 0) or 0)
                product.manage_stock = request.form.get('manage_stock') == 'on'

            
            # Auto-calculate on_sale status
            product.on_sale = product.sale_price is not None and product.sale_price > 0
            
            product.stock_status = request.form.get('stock_status', 'in_stock')
            product.status = request.form.get('status', 'draft')
            product.requires_sizing = request.form.get('requires_sizing') == 'on'
            product.sizing_type = request.form.get('sizing_type', '').strip() or None if request.form.get('requires_sizing') == 'on' else None
            product.sizing_options = json.loads(request.form.get('sizing_options', '[]')) if request.form.get('requires_sizing') == 'on' and request.form.get('sizing_options') else None
            product.disable_cod = request.form.get('disable_cod') == 'on'
            
            # Payment & Sizing Options
            product.payment_option = request.form.get('payment_option', 'cod_available')
            product.advance_payment_amount = Decimal(request.form.get('advance_payment_amount', 0) or 0) if product.payment_option == 'partial_advance' else None
            product.sizing_consultation_required = request.form.get('sizing_consultation_required') == 'on'
            
            product.meta_title = request.form.get('meta_title', '').strip() or None
            product.meta_description = request.form.get('meta_description', '').strip() or None
            product.meta_keywords = request.form.get('meta_keywords', '').strip() or None
            
            product.gender = request.form.getlist('gender') if request.form.getlist('gender') else None
            
            # Country Availability
            available_countries_data = request.form.get('available_countries')
            if available_countries_data:
                try:
                    product.available_countries = json.loads(available_countries_data)
                except:
                    product.available_countries = None
            else:
                product.available_countries = None
            
            # Update categories
            product.categories.clear()
            category_ids = request.form.getlist('categories')
            for category_id in category_ids:
                category = Category.query.get(int(category_id))
                if category:
                    product.categories.append(category)
            
            # Update tags - split comma-separated string
            product.tags.clear()
            tags_input = request.form.get('tags', '').strip()
            if tags_input:
                tag_names = [t.strip() for t in tags_input.split(',') if t.strip()]
                for tag_name in tag_names:
                    tag = Tag.query.filter_by(name=tag_name).first()
                    if not tag:
                        tag = Tag(name=tag_name, slug=generate_slug(tag_name))
                        db.session.add(tag)
                    product.tags.append(tag)
            
            # Update attributes (delete old ones and recreate)
            if product.product_type == 'variable':
                # First delete attribute terms (child records)
                existing_attrs = ProductAttribute.query.filter_by(product_id=product.id).all()
                for attr in existing_attrs:
                    ProductAttributeTerm.query.filter_by(attribute_id=attr.id).delete()
                # Then delete attributes (parent records)
                ProductAttribute.query.filter_by(product_id=product.id).delete()
                attr_names = request.form.getlist('attr_name[]')
                attr_values = request.form.getlist('attr_values[]')
                # Use hidden inputs to track checkbox states (always submitted regardless of checked state)
                attr_visible_idx = request.form.getlist('attr_visible_idx[]')
                attr_use_for_variations_idx = request.form.getlist('attr_use_for_variations_idx[]')
                
                for idx, attr_name in enumerate(attr_names):
                    if attr_name and attr_name.strip():
                        # Check if checkbox was checked by checking the hidden input value
                        visible = idx < len(attr_visible_idx) and attr_visible_idx[idx] == '1'
                        use_for_variations = idx < len(attr_use_for_variations_idx) and attr_use_for_variations_idx[idx] == '1'
                        
                        attr = ProductAttribute(
                            product_id=product.id,
                            name=attr_name.strip(),
                            visible=visible,
                            use_for_variations=use_for_variations
                        )
                        db.session.add(attr)
                        db.session.flush()
                        
                        if idx < len(attr_values) and attr_values[idx]:
                            term_names = [t.strip() for t in attr_values[idx].split(',') if t.strip()]
                            for term_name in term_names:
                                term_slug = generate_slug(term_name)
                                term = ProductAttributeTerm(
                                    attribute_id=attr.id,
                                    name=term_name,
                                    slug=term_slug
                                )
                                db.session.add(term)
            
            # Update variations (delete old ones and recreate)
            if product.product_type == 'variable':
                ProductVariation.query.filter_by(product_id=product.id).delete()
                variation_attrs = request.form.getlist('variation_attributes[]')
                variation_skus = request.form.getlist('variation_sku[]')
                variation_regular_prices = request.form.getlist('variation_regular_price[]')
                variation_sale_prices = request.form.getlist('variation_sale_price[]')
                variation_stocks = request.form.getlist('variation_stock[]')
                variation_images = request.form.getlist('variation_images[]')
                
                for idx, var_attrs in enumerate(variation_attrs):
                    if not var_attrs.strip():
                        continue
                    
                    attr_dict = {}
                    for pair in var_attrs.split('|'):
                        if ':' in pair:
                            key, val = pair.split(':', 1)
                            attr_dict[key.strip()] = val.strip()
                    
                    var_sku = variation_skus[idx] if idx < len(variation_skus) else None
                    if var_sku and ProductVariation.query.filter_by(sku=var_sku).first():
                        var_sku = f"{var_sku}-{product.id}-{idx}"
                    
                    variation = ProductVariation(
                        product_id=product.id,
                        sku=var_sku.strip() if var_sku else None,
                        regular_price=Decimal(variation_regular_prices[idx] or 0) if idx < len(variation_regular_prices) and variation_regular_prices[idx] else None,
                        sale_price=Decimal(variation_sale_prices[idx] or 0) if idx < len(variation_sale_prices) and variation_sale_prices[idx] else None,
                        stock_quantity=int(variation_stocks[idx] or 0) if idx < len(variation_stocks) else 0,
                        manage_stock=True if idx < len(variation_stocks) and variation_stocks[idx] else False,
                        attribute_terms=attr_dict,
                        image_url=variation_images[idx].strip() if idx < len(variation_images) and variation_images[idx] else None,
                        status='publish'
                    )
                    db.session.add(variation)
            
            # Handle image deletions (from existing images)
            delete_image_ids = request.form.get('delete_images', '').split(',')
            for img_id in delete_image_ids:
                if img_id and img_id.strip():
                    try:
                        img_id_int = int(img_id.strip())
                        image_to_delete = ProductImage.query.get(img_id_int)
                        # Ensure we only delete images belonging to this product
                        if image_to_delete and image_to_delete.product_id == product.id:
                            # Optional: delete file from disk
                            try:
                                delete_file_local(image_to_delete.image_url)
                            except Exception as e:
                                print(f"Error deleting file for image {img_id}: {e}")
                            
                            db.session.delete(image_to_delete)
                    except Exception as e:
                        print(f"Error processing image deletion for {img_id}: {e}")

            # Handle New Media from Modal
            new_media_urls_json = request.form.get('new_media_urls', '[]')
            primary_identifier = request.form.get('primary_image_identifier', '')
            
            try:
                new_media_urls = json.loads(new_media_urls_json)
            except:
                new_media_urls = []
            
            # Update Primary Image (Existing)
            if primary_identifier.startswith('id:'):
                try:
                    primary_id = int(primary_identifier.split(':')[1])
                    # Reset all
                    ProductImage.query.filter_by(product_id=product.id).update({'is_primary': False})
                    # Set new primary
                    new_primary = ProductImage.query.get(primary_id)
                    if new_primary and new_primary.product_id == product.id:
                        new_primary.is_primary = True
                except:
                    pass
            
            # Determine ordering
            current_max_order = db.session.query(db.func.max(ProductImage.image_order)).filter_by(product_id=product.id).scalar()
            image_order = (current_max_order + 1) if current_max_order is not None else 0
            
            # If we already have a primary (either existing or just set above), we don't auto-set next
            primary_exists = ProductImage.query.filter_by(product_id=product.id, is_primary=True).first() is not None

            # Add New Images
            for url in new_media_urls:
                if url:
                    # Check if this specific URL is marked as primary (and it's not an ID)
                    is_primary = (url == primary_identifier)
                    
                    if is_primary:
                        # Ensure we unset others if this one is the new primary
                        ProductImage.query.filter_by(product_id=product.id).update({'is_primary': False})
                        primary_exists = True
                    
                    product_image = ProductImage(
                        product_id=product.id,
                        image_url=url,
                        image_order=image_order,
                        alt_text='',
                        is_primary=is_primary
                    )
                    db.session.add(product_image)
                    image_order += 1
            
            # Handle Legacy Uploads (Fallback)
            image_files = request.files.getlist('images')
            for image_file in image_files:
                if image_file and image_file.filename and allowed_file(image_file.filename):
                    try:
                        image_url = upload_file_local(image_file, folder='products')
                        
                        is_primary = False
                        if not primary_exists:
                            is_primary = True
                            primary_exists = True
                        
                        product_image = ProductImage(
                            product_id=product.id,
                            image_url=image_url,
                            image_order=image_order,
                            alt_text='',
                            is_primary=is_primary
                        )
                        db.session.add(product_image)
                        image_order += 1
                    except Exception as e:
                        print(f"Error uploading image: {e}")


            # Check for Primary Image Update (from existing images)
            new_primary_index = request.form.get('primary_image')
            if new_primary_index is not None:
                # This logic might need refinement if the UI passes ID or Index. 
                # Assuming UI passes index in the list, but for edit we might need ID.
                # For now, let's rely on the add logic above for new images.
                # If the user selected an existing image as primary, we'd need to handle that separately
                # but typically that's done via a separate AJAX call or specialized input.
                pass 

        

            db.session.commit()
            
            flash('Product updated successfully!', 'success')
            return redirect(url_for('products.edit', id=product.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating product: {str(e)}', 'error')
            print(f"Error: {e}")
    

    return render_template('products/create_edit.html',
                         product=product,
                         categories=get_all_categories(),
                         tags=get_all_tags(),
                         shipping_classes=ShippingClass.query.order_by(ShippingClass.name).all(),
                         all_products=Product.query.filter(Product.status == 'published').order_by(Product.title).all(),
                        )

@products.route('/bulk-action', methods=['POST'])
@login_required
def bulk_action():
    """Handle bulk actions on products"""
    action = request.form.get('action')
    product_ids = request.form.getlist('product_ids')
    
    if not action or not product_ids:
        flash('Please select an action and at least one product.', 'error')
        return redirect(url_for('products.list'))
    
    try:
        products = Product.query.filter(Product.id.in_([int(pid) for pid in product_ids])).all()
        
        if action == 'delete':
            for product in products:
                # Delete images from local storage
                for image in product.images:
                    try:
                        delete_file_local(image.image_url)
                    except:
                        pass
                db.session.delete(product)
            flash(f'{len(products)} product(s) deleted successfully!', 'success')
        elif action == 'publish':
            for product in products:
                product.status = 'published'
            flash(f'{len(products)} product(s) published successfully!', 'success')
        elif action == 'draft':
            for product in products:
                product.status = 'draft'
            flash(f'{len(products)} product(s) moved to draft successfully!', 'success')
        elif action == 'private':
            for product in products:
                product.status = 'private'
            flash(f'{len(products)} product(s) moved to private successfully!', 'success')
        
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Error performing bulk action: {str(e)}', 'error')
        print(f"Error: {e}")
    
    # Preserve filters in redirect
    return redirect(request.referrer or url_for('products.list'))

@products.route('/<int:id>/toggle-featured', methods=['POST'])
@login_required
def toggle_featured(id):
    """Toggle featured status of a product"""
    product = Product.query.get_or_404(id)
    
    try:
        product.featured = not product.featured
        db.session.commit()
        
        return jsonify({
            'success': True,
            'featured': product.featured,
            'message': 'Featured status updated successfully!'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error updating featured status: {str(e)}'
        }), 500

@products.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Delete product"""
    product = Product.query.get_or_404(id)
    
    try:
        # Delete images from local storage
        for image in product.images:
            delete_file_local(image.image_url)
        
        db.session.delete(product)
        db.session.commit()
        
        flash('Product deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting product: {str(e)}', 'error')
        print(f"Error: {e}")
    
    return redirect(url_for('products.list'))

@products.route('/<int:id>/generate-variations', methods=['POST'])
@login_required
def generate_variations(id):
    """Generate variations from product attributes"""
    product = Product.query.get_or_404(id)
    
    if product.product_type != 'variable':
        return jsonify({'error': 'Product must be variable type'}), 400
    
    try:
        # Get attributes marked for variations
        variation_attrs = [attr for attr in product.attributes if attr.use_for_variations]
        
        if not variation_attrs:
            return jsonify({'error': 'No attributes marked for variations'}), 400
        
        # Generate all combinations
        attr_combinations = []
        for attr in variation_attrs:
            attr_combinations.append([term.name for term in attr.terms])
        
        variations = []
        for combo in itertools_product(*attr_combinations):
            attr_dict = {}
            for idx, attr in enumerate(variation_attrs):
                attr_dict[attr.name] = combo[idx]
            variations.append(attr_dict)
        
        return jsonify({'variations': variations, 'count': len(variations)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@products.route('/import', methods=['GET', 'POST'])
@login_required
def import_csv():
    """CSV import page"""
    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash('Please select a CSV file.', 'error')
            return redirect(url_for('products.import_csv'))
        
        csv_file = request.files['csv_file']
        if csv_file.filename == '':
            flash('Please select a CSV file.', 'error')
            return redirect(url_for('products.import_csv'))
        
        if not csv_file.filename.endswith('.csv'):
            flash('Please upload a CSV file.', 'error')
            return redirect(url_for('products.import_csv'))
        
        download_images = request.form.get('download_images', 'off') == 'on'
        
        try:
            results = parse_woocommerce_csv(csv_file, download_images=download_images)
            
            if results['errors']:
                error_msg = f"Import completed with {len(results['errors'])} errors. "
                error_msg += f"Created: {results['created']}, Updated: {results['updated']}, Skipped: {results['skipped']}"
                flash(error_msg, 'info')
                
                # Show first few errors
                error_details = '; '.join(results['errors'][:5])
                if len(results['errors']) > 5:
                    error_details += f" ... and {len(results['errors']) - 5} more"
                flash(f"Errors: {error_details}", 'error')
            else:
                flash(f"Import successful! Created: {results['created']}, Updated: {results['updated']}, Skipped: {results['skipped']}", 'success')
            
            return redirect(url_for('products.list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error importing CSV: {str(e)}', 'error')
            print(f"CSV import error: {e}")
    
    return render_template('products/import.html')

# Helper functions
def get_all_categories():
    """Get all categories"""
    return Category.query.order_by(Category.name).all()

def get_all_tags():
    """Get all tags"""
    return Tag.query.order_by(Tag.name).all()

from datetime import datetime

