import csv
import io
from decimal import Decimal
from datetime import datetime
from flask import current_app
from models import db
from models.product import Product, ProductImage, Category, Tag, ProductAttribute, ProductAttributeTerm, ProductVariation
from utils.validators import generate_slug
from utils.upload import download_file_from_url


def _get_or_create_category(cat_name, parent_category=None):
    """Get or create a category with proper hierarchy and slug handling"""
    # Check if category exists with this name and parent
    if parent_category:
        category = Category.query.filter_by(name=cat_name, parent_id=parent_category.id).first()
    else:
        category = Category.query.filter_by(name=cat_name, parent_id=None).first()
    
    if not category:
        # Generate slug - if it conflicts, append parent slug or counter
        base_slug = generate_slug(cat_name)
        slug = base_slug
        
        # If parent exists, try parent-slug format first
        if parent_category:
            parent_slug = parent_category.slug
            slug = f"{parent_slug}-{base_slug}"
            # Check if this slug already exists
            if Category.query.filter_by(slug=slug).first():
                slug = base_slug  # Fall back to base slug
        
        # Ensure slug uniqueness
        counter = 1
        original_slug = slug
        while Category.query.filter_by(slug=slug).first():
            slug = f"{original_slug}-{counter}"
            counter += 1
        
        category = Category(
            name=cat_name,
            slug=slug,
            parent_id=parent_category.id if parent_category else None
        )
        db.session.add(category)
        db.session.flush()
    
    return category


def parse_woocommerce_csv(csv_file, download_images=True):
    """
    Parse WooCommerce CSV and import products
    
    Args:
        csv_file: File object containing CSV data
        download_images: Boolean - if True, download images to R2, else keep URLs
    
    Returns:
        dict: Import results with stats and errors
    """

    
    results = {
        'created': 0,
        'updated': 0,
        'skipped': 0,
        'errors': []
    }
    
    try:
        # Read CSV content
        if isinstance(csv_file, bytes):
            csv_content = csv_file.decode('utf-8-sig')
        else:
            csv_content = csv_file.read()
            if isinstance(csv_content, bytes):
                csv_content = csv_content.decode('utf-8-sig')
        
        csv_reader = csv.DictReader(io.StringIO(csv_content))
        
        # Track parent products for variations - store multiple formats for reliable lookup
        parent_products = {}  # {woocommerce_id: product_id} - stores both original and normalized formats
        sku_to_product_id = {}  # {sku: product_id} - for SKU fallback lookup
        
        def normalize_id(id_str):
            """Normalize WooCommerce ID (handles scientific notation like 9.76605E+12)"""
            if not id_str:
                return None
            try:
                if 'E' in id_str.upper() or 'e' in id_str:
                    return str(int(float(id_str)))
                else:
                    return id_str.strip()
            except (ValueError, OverflowError):
                return id_str.strip()
        
        # Process rows
        for row_idx, row in enumerate(csv_reader, start=2):  # Start at 2 because row 1 is header
            try:
                product_type = row.get('Type', 'simple').lower().strip()
                
                if product_type == 'variation':
                    # Handle variation
                    parent_id_str = row.get('Parent', '').strip()
                    if not parent_id_str:
                        results['errors'].append(f"Row {row_idx}: Variation missing Parent ID")
                        results['skipped'] += 1
                        continue
                    
                    # Normalize Parent ID
                    parent_id_normalized = normalize_id(parent_id_str)
                    
                    # Find parent product by WooCommerce ID (try multiple formats)
                    parent_product_id = parent_products.get(parent_id_normalized)
                    
                    if not parent_product_id:
                        # Try original format
                        parent_product_id = parent_products.get(parent_id_str)
                    
                    if not parent_product_id:
                        # Try SKU fallback (variable products often have SKU matching WooCommerce ID)
                        parent_product_id = sku_to_product_id.get(parent_id_str)
                    
                    if not parent_product_id and parent_id_normalized:
                        # Try normalized ID as SKU
                        parent_product_id = sku_to_product_id.get(parent_id_normalized)
                    
                    if not parent_product_id:
                        # Last resort: try to find by SKU query
                        parent_product = Product.query.filter_by(sku=parent_id_str).first()
                        if not parent_product and parent_id_normalized:
                            parent_product = Product.query.filter_by(sku=parent_id_normalized).first()
                        
                        if parent_product:
                            parent_product_id = parent_product.id
                            # Cache for future lookups
                            if parent_id_normalized:
                                parent_products[parent_id_normalized] = parent_product_id
                            parent_products[parent_id_str] = parent_product_id
                            sku_to_product_id[parent_id_str] = parent_product_id
                            if parent_id_normalized != parent_id_str:
                                sku_to_product_id[parent_id_normalized] = parent_product_id
                        else:
                            results['errors'].append(f"Row {row_idx}: Parent product {parent_id_str} ({parent_id_normalized}) not found. Make sure parent variable product is imported before variations.")
                            results['skipped'] += 1
                            continue
                    
                    # Import variation
                    _import_variation(row, parent_product_id, download_images, results, row_idx)
                
                elif product_type in ['simple', 'variable', 'external']:
                    # Handle product
                    sku = row.get('SKU', '').strip()
                    if not sku:
                        results['errors'].append(f"Row {row_idx}: Missing SKU")
                        results['skipped'] += 1
                        continue
                    
                    # Check if product exists
                    product = Product.query.filter_by(sku=sku).first()
                    woocommerce_id = row.get('ID', '').strip()
                    
                    # Handle WooCommerce ID (might be scientific notation)
                    woocommerce_id_normalized = normalize_id(woocommerce_id) if woocommerce_id else None
                    
                    if product:
                        _update_product(product, row, download_images, results, row_idx)
                        # Update parent mapping if product was updated
                        if woocommerce_id_normalized:
                            parent_products[woocommerce_id_normalized] = product.id
                        if woocommerce_id:
                            parent_products[woocommerce_id] = product.id
                        sku_to_product_id[sku] = product.id
                    else:
                        product = _create_product(row, download_images, results, row_idx)
                        if product:
                            # Store parent mapping with both formats
                            if woocommerce_id_normalized:
                                parent_products[woocommerce_id_normalized] = product.id
                            if woocommerce_id:
                                parent_products[woocommerce_id] = product.id
                            sku_to_product_id[sku] = product.id
                else:
                    results['skipped'] += 1
                        
            except Exception as e:
                results['errors'].append(f"Row {row_idx}: {str(e)}")
                results['skipped'] += 1
                db.session.rollback()
        
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        results['errors'].append(f"CSV parsing error: {str(e)}")
    
    return results


def _create_product(row, download_images, results, row_idx):
    """Create a new product from CSV row"""
    try:
        sku = row.get('SKU', '').strip()
        name = row.get('Name', '').strip()
        
        if not name:
            results['errors'].append(f"Row {row_idx}: Missing product name")
            return None
        
        slug = row.get('Name', '').strip()
        if slug:
            slug = generate_slug(slug)
            # Ensure uniqueness
            counter = 1
            original_slug = slug
            while Product.query.filter_by(slug=slug).first():
                slug = f"{original_slug}-{counter}"
                counter += 1
        
        product_type = row.get('Type', 'simple').lower().strip()
        
        product = Product(
            title=name,
            slug=slug,
            product_type=product_type,
            short_description=row.get('Short description', '').strip() or None,
            description=row.get('Description', '').strip() or None,
            sku=sku or None,
            regular_price=Decimal(row.get('Regular price', 0) or 0),
            sale_price=Decimal(row.get('Sale price', 0) or 0) if row.get('Sale price') else None,
            stock_quantity=int(row.get('Stock', 0) or 0),
            manage_stock=row.get('In stock?', '').strip().lower() == '1',
            stock_status='in_stock' if row.get('In stock?', '').strip().lower() == '1' else 'out_of_stock',
            weight=Decimal(row.get('Weight (kg)', 0) or 0) if row.get('Weight (kg)') else None,
            length=Decimal(row.get('Length (in)', 0) or 0) if row.get('Length (in)') else None,
            width=Decimal(row.get('Width (in)', 0) or 0) if row.get('Width (in)') else None,
            height=Decimal(row.get('Height (in)', 0) or 0) if row.get('Height (in)') else None,
            dimensions_unit='in' if row.get('Length (in)') else 'cm',
            status='published' if row.get('Published', '').strip() == '1' else 'draft',
            featured=row.get('Is featured?', '').strip() == '1',
            on_sale=bool(row.get('Sale price', '').strip()),
            external_url=row.get('External URL', '').strip() or None if product_type == 'external' else None,
            button_text=row.get('Button text', '').strip() or None if product_type == 'external' else None,
        )
        
        db.session.add(product)
        db.session.flush()
        
        # Handle categories - WooCommerce format: "Category1, Category2 > Child, Category3"
        categories_str = row.get('Categories', '').strip()
        if categories_str:
            # Split by comma first to get individual category paths
            category_paths = [path.strip() for path in categories_str.split(',') if path.strip()]
            
            for category_path in category_paths:
                # Split by > to get hierarchy: "Dress > Dance Practic" -> ["Dress", "Dance Practic"]
                path_parts = [p.strip() for p in category_path.split('>') if p.strip()]
                
                if not path_parts:
                    continue
                
                parent_category = None
                # Build hierarchy from top to bottom
                for idx, cat_name in enumerate(path_parts):
                    category = _get_or_create_category(cat_name, parent_category)
                    parent_category = category
                
                # Add the final category (leaf) to the product
                if category and category not in product.categories:
                    product.categories.append(category)
        
        # Handle tags
        tags_str = row.get('Tags', '').strip()
        if tags_str:
            tag_names = [t.strip() for t in tags_str.split(',') if t.strip()]
            for tag_name in tag_names:
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name, slug=generate_slug(tag_name))
                    db.session.add(tag)
                    db.session.flush()
                product.tags.append(tag)
        
        # Handle images
        images_str = row.get('Images', '').strip()
        if images_str:
            image_urls = [url.strip() for url in images_str.split(',') if url.strip()]
            for idx, img_url in enumerate(image_urls):
                try:
                    # Only download if explicitly requested
                    if download_images:
                        final_url = download_file_from_url(img_url, folder='products')
                    else:
                        # Keep URL as-is when download_images is False
                        final_url = img_url.strip()
                    
                    product_image = ProductImage(
                        product_id=product.id,
                        image_url=final_url,
                        image_order=idx,
                        alt_text=name,
                        is_primary=(idx == 0)
                    )
                    db.session.add(product_image)
                except Exception as e:
                    # Only report errors if we were trying to download
                    if download_images:
                        results['errors'].append(f"Row {row_idx}: Error downloading image {img_url}: {str(e)}")
                    else:
                        # If keeping URLs, just use the URL as-is even if there's an error
                        product_image = ProductImage(
                            product_id=product.id,
                            image_url=img_url.strip(),
                            image_order=idx,
                            alt_text=name,
                            is_primary=(idx == 0)
                        )
                        db.session.add(product_image)
        
        # Handle attributes for variable products
        if product_type == 'variable':
            for attr_num in range(1, 6):  # WooCommerce supports up to 5 attributes
                attr_name = row.get(f'Attribute {attr_num} name', '').strip()
                if not attr_name:
                    continue
                
                attr_values_str = row.get(f'Attribute {attr_num} value(s)', '').strip()
                if not attr_values_str:
                    continue
                
                attr_visible = row.get(f'Attribute {attr_num} visible', '').strip() == '1'
                attr_use_for_variations = row.get(f'Attribute {attr_num} global', '').strip() == '1'  # Adjust logic as needed
                
                attr = ProductAttribute(
                    product_id=product.id,
                    name=attr_name,
                    visible=attr_visible,
                    use_for_variations=attr_use_for_variations
                )
                db.session.add(attr)
                db.session.flush()
                
                # Add terms
                term_values = [v.strip() for v in attr_values_str.split(',') if v.strip()]
                for term_value in term_values:
                    term_slug = generate_slug(term_value)
                    term = ProductAttributeTerm(
                        attribute_id=attr.id,
                        name=term_value,
                        slug=term_slug
                    )
                    db.session.add(term)
        
        results['created'] += 1
        return product
        
    except Exception as e:
        results['errors'].append(f"Row {row_idx}: Error creating product: {str(e)}")
        return None


def _update_product(product, row, download_images, results, row_idx):
    """Update existing product from CSV row"""
    try:
        product.title = row.get('Name', product.title).strip()
        product.short_description = row.get('Short description', '').strip() or None
        product.description = row.get('Description', '').strip() or None
        product.regular_price = Decimal(row.get('Regular price', 0) or 0)
        product.sale_price = Decimal(row.get('Sale price', 0) or 0) if row.get('Sale price') else None
        product.stock_quantity = int(row.get('Stock', 0) or 0)
        product.status = 'published' if row.get('Published', '').strip() == '1' else 'draft'
        
        # Update categories - WooCommerce format: "Category1, Category2 > Child, Category3"
        categories_str = row.get('Categories', '').strip()
        if categories_str:
            # Clear existing categories
            product.categories.clear()
            
            # Split by comma first to get individual category paths
            category_paths = [path.strip() for path in categories_str.split(',') if path.strip()]
            
            for category_path in category_paths:
                # Split by > to get hierarchy: "Dress > Dance Practic" -> ["Dress", "Dance Practic"]
                path_parts = [p.strip() for p in category_path.split('>') if p.strip()]
                
                if not path_parts:
                    continue
                
                parent_category = None
                # Build hierarchy from top to bottom
                for idx, cat_name in enumerate(path_parts):
                    category = _get_or_create_category(cat_name, parent_category)
                    parent_category = category
                
                # Add the final category (leaf) to the product
                if category and category not in product.categories:
                    product.categories.append(category)
        
        # Update images if provided
        images_str = row.get('Images', '').strip()
        if images_str:
            # Clear old images
            ProductImage.query.filter_by(product_id=product.id).delete()
            
            image_urls = [url.strip() for url in images_str.split(',') if url.strip()]
            for idx, img_url in enumerate(image_urls):
                try:
                    # Only download if explicitly requested
                    if download_images:
                        final_url = download_file_from_url(img_url, folder='products')
                    else:
                        # Keep URL as-is when download_images is False
                        final_url = img_url.strip()
                    
                    product_image = ProductImage(
                        product_id=product.id,
                        image_url=final_url,
                        image_order=idx,
                        alt_text=product.title,
                        is_primary=(idx == 0)
                    )
                    db.session.add(product_image)
                except Exception as e:
                    # Only report errors if we were trying to download
                    if download_images:
                        results['errors'].append(f"Row {row_idx}: Error downloading image {img_url}: {str(e)}")
                    else:
                        # If keeping URLs, just use the URL as-is even if there's an error
                        product_image = ProductImage(
                            product_id=product.id,
                            image_url=img_url.strip(),
                            image_order=idx,
                            alt_text=product.title,
                            is_primary=(idx == 0)
                        )
                        db.session.add(product_image)
        
        results['updated'] += 1
        
    except Exception as e:
        results['errors'].append(f"Row {row_idx}: Error updating product: {str(e)}")


def _import_variation(row, parent_product_id, download_images, results, row_idx):
    """Import a product variation"""
    try:
        sku = row.get('SKU', '').strip()
        name = row.get('Name', '').strip()
        
        # Parse attributes from variation name or attribute columns
        attr_dict = {}
        for attr_num in range(1, 6):
            attr_name = row.get(f'Attribute {attr_num} name', '').strip()
            if attr_name:
                attr_value = row.get(f'Attribute {attr_num} value(s)', '').strip()
                if attr_value:
                    attr_dict[attr_name] = attr_value
        
        # Check if variation exists
        variation = None
        if sku:
            variation = ProductVariation.query.filter_by(sku=sku, product_id=parent_product_id).first()
        
        variation_data = {
            'product_id': parent_product_id,
            'sku': sku or None,
            'regular_price': Decimal(row.get('Regular price', 0) or 0) if row.get('Regular price') else None,
            'sale_price': Decimal(row.get('Sale price', 0) or 0) if row.get('Sale price') else None,
            'stock_quantity': int(row.get('Stock', 0) or 0),
            'manage_stock': row.get('In stock?', '').strip().lower() == '1',
            'stock_status': 'in_stock' if row.get('In stock?', '').strip().lower() == '1' else 'out_of_stock',
            'weight': Decimal(row.get('Weight (kg)', 0) or 0) if row.get('Weight (kg)') else None,
            'length': Decimal(row.get('Length (in)', 0) or 0) if row.get('Length (in)') else None,
            'width': Decimal(row.get('Width (in)', 0) or 0) if row.get('Width (in)') else None,
            'height': Decimal(row.get('Height (in)', 0) or 0) if row.get('Height (in)') else None,
            'dimensions_unit': 'in' if row.get('Length (in)') else 'cm',
            'attribute_terms': attr_dict,
            'status': 'publish'
        }
        
        # Handle variation image
        images_str = row.get('Images', '').strip()
        if images_str:
            img_url = images_str.split(',')[0].strip()  # Take first image
            try:
                # Only download if explicitly requested
                if download_images:
                    variation_data['image_url'] = download_file_from_url(img_url, folder='products')
                else:
                    # Keep URL as-is when download_images is False
                    variation_data['image_url'] = img_url.strip()
            except Exception as e:
                # Only report errors if we were trying to download
                if download_images:
                    results['errors'].append(f"Row {row_idx}: Error downloading variation image {img_url}: {str(e)}")
                else:
                    # If keeping URLs, just use the URL as-is
                    variation_data['image_url'] = img_url.strip()
        
        if variation:
            # Update existing
            for key, value in variation_data.items():
                setattr(variation, key, value)
        else:
            # Create new
            variation = ProductVariation(**variation_data)
            db.session.add(variation)
        
        results['created'] += 1
        
    except Exception as e:
        results['errors'].append(f"Row {row_idx}: Error importing variation: {str(e)}")

