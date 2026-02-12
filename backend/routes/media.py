from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from utils.permissions import login_required
from models import db
from models.product import ProductImage, ProductVariation, Category
from models.deal import Deal
from utils.upload import delete_file_local
import os

media = Blueprint('media', __name__, url_prefix='/admin/media')

@media.route('/api/list')
@login_required
def api_list_media():
    """API endpoint to list media files for the modal"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').lower()
    
    # 1. Get all files from uploads directory
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    upload_folder = os.path.join(base_dir, 'uploads')
    
    all_files = []
    
    if os.path.exists(upload_folder):
        for root, dirs, files in os.walk(upload_folder):
            for file in files:
                if file.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg')):
                    rel_dir = os.path.relpath(root, base_dir)
                    url_path = f"/{rel_dir}/{file}".replace('\\', '/')
                    
                    if search and search not in file.lower():
                        continue
                        
                    full_path = os.path.join(root, file)
                    size = os.path.getsize(full_path)
                    created = os.path.getctime(full_path)
                    
                    all_files.append({
                        'url': url_path,
                        'name': file,
                        'folder': os.path.basename(root),
                        'size': size,
                        'created': created
                    })
    
    # Sort by date desc
    all_files.sort(key=lambda x: x['created'], reverse=True)
    
    # Pagination
    per_page = 24
    total_files = len(all_files)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_files = all_files[start:end]
    
    return jsonify({
        'files': paginated_files,
        'page': page,
        'total_count': total_files,
        'has_next': end < total_files
    })

@media.route('/api/upload', methods=['POST'])
@login_required
def api_upload():
    """API endpoint for file uploads"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    if file:
        try:
            from utils.upload import upload_file_local
            image_url = upload_file_local(file, folder='media_library')
            
            # Return file info
            return jsonify({
                'success': True,
                'file': {
                    'url': image_url,
                    'name': os.path.basename(image_url)
                }
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500
            
    return jsonify({'error': 'Unknown error'}), 400


@media.route('/')
@login_required
def list_media():
    """List all media files with usage status"""
    filter_status = request.args.get('status', 'all') # all, used, unused
    page = request.args.get('page', 1, type=int)
    
    # 1. Get all files from uploads directory
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    upload_folder = os.path.join(base_dir, 'uploads')
    
    all_files = []
    
    if os.path.exists(upload_folder):
        for root, dirs, files in os.walk(upload_folder):
            for file in files:
                if file.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg')):
                    # Create relative path used in DB
                    # root is e.g. .../uploads/products
                    rel_dir = os.path.relpath(root, base_dir)
                    url_path = f"/{rel_dir}/{file}".replace('\\', '/')
                    
                    full_path = os.path.join(root, file)
                    size = os.path.getsize(full_path)
                    created = os.path.getctime(full_path)
                    
                    all_files.append({
                        'url': url_path,
                        'name': file,
                        'folder': os.path.basename(root),
                        'size': size,
                        'created': created
                    })
    
    # 2. Get all used image URLs
    used_urls = set()
    
    # Product Images
    for img in db.session.query(ProductImage.image_url).all():
        if img.image_url:
            used_urls.add(img.image_url)
            
    # Category Images
    for img in db.session.query(Category.image_url).all():
        if img.image_url:
            used_urls.add(img.image_url)
            
    # Variation Images
    for img in db.session.query(ProductVariation.image_url).all():
        if img.image_url:
            used_urls.add(img.image_url)

    # Deal Featured Images
    for img in db.session.query(Deal.featured_image).all():
        if img.featured_image:
            used_urls.add(img.featured_image)
            
    # Mark status
    final_list = []
    for f in all_files:
        is_used = f['url'] in used_urls
        f['status'] = 'used' if is_used else 'unused'
        
        if filter_status == 'all':
            final_list.append(f)
        elif filter_status == 'used' and is_used:
            final_list.append(f)
        elif filter_status == 'unused' and not is_used:
            final_list.append(f)
            
    # Sort by date desc (newest first)
    final_list.sort(key=lambda x: x['created'], reverse=True)
    
    # Simple pagination
    per_page = 50
    total_files = len(final_list)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_files = final_list[start:end]
    
    total_pages = (total_files + per_page - 1) // per_page
    
    return render_template('media/list.html', 
                         files=paginated_files,
                         page=page,
                         total_pages=total_pages,
                         current_status=filter_status,
                         total_count=total_files)

@media.route('/delete', methods=['POST'])
@login_required
def delete_media():
    """Delete a media file"""
    file_url = request.form.get('file_url')
    
    if not file_url:
        flash('No file specified', 'error')
        return redirect(url_for('media.list_media'))
        
    # Check if used
    is_used = False
    if ProductImage.query.filter_by(image_url=file_url).first(): is_used = True
    if Category.query.filter_by(image_url=file_url).first(): is_used = True
    if ProductVariation.query.filter_by(image_url=file_url).first(): is_used = True
    if Deal.query.filter_by(featured_image=file_url).first(): is_used = True
    
    if is_used:
        flash('Cannot delete file: It is currently in use.', 'error')
        return redirect(url_for('media.list_media'))
        
    if delete_file_local(file_url):
        flash('File deleted successfully', 'success')
    else:
        flash('Error deleting file', 'error')
        
    return redirect(url_for('media.list_media'))

@media.route('/bulk-delete', methods=['POST'])
@login_required
def bulk_delete():
    """Delete multiple media files"""
    file_urls = request.form.getlist('file_urls')
    
    if not file_urls:
        flash('No files selected', 'error')
        return redirect(url_for('media.list_media'))
        
    deleted_count = 0
    errors = 0
    
    # Pre-fetch usage data to avoid N+1 queries
    used_urls = set()
    for img in db.session.query(ProductImage.image_url).all(): used_urls.add(img.image_url)
    for img in db.session.query(Category.image_url).all(): used_urls.add(img.image_url)
    for img in db.session.query(ProductVariation.image_url).all(): used_urls.add(img.image_url)
    for img in db.session.query(Deal.featured_image).all(): used_urls.add(img.featured_image)
    
    for file_url in file_urls:
        if file_url in used_urls:
            errors += 1
            print(f"Skipping used file: {file_url}")
            continue
            
        if delete_file_local(file_url):
            deleted_count += 1
        else:
            errors += 1
            
    if deleted_count > 0:
        flash(f'Successfully deleted {deleted_count} files.', 'success')
    
    if errors > 0:
        flash(f'{errors} files could not be deleted (they might be in use or missing).', 'warning')
        
    return redirect(url_for('media.list_media'))

@media.route('/convert-webp', methods=['POST'])
@login_required
def convert_webp():
    """Convert selected files to WebP and update DB references"""
    file_urls = request.form.getlist('file_urls')
    
    if not file_urls:
        flash('No files selected', 'error')
        return redirect(url_for('media.list_media'))
        
    from utils.upload import convert_to_webp
    from models.product import Product
    
    converted_count = 0
    updated_references = 0
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    for file_url in file_urls:
        if file_url.lower().endswith('.webp'):
            continue
            
        # Determine local path
        if file_url.startswith('/uploads/'):
            rel_path = file_url.lstrip('/')
            full_path = os.path.join(base_dir, rel_path.replace('/', os.sep))
        else:
            continue
            
        if os.path.exists(full_path):
            new_path = convert_to_webp(full_path)
            
            if new_path != full_path:
                converted_count += 1
                
                # New URL
                new_filename = os.path.basename(new_path)
                folder = os.path.basename(os.path.dirname(new_path))
                new_url = f"/uploads/{folder}/{new_filename}"
                
                # Update DB References
                # ProductImage
                for row in ProductImage.query.filter_by(image_url=file_url).all():
                    row.image_url = new_url
                    updated_references += 1
                    
                # Category
                for row in Category.query.filter_by(image_url=file_url).all():
                    row.image_url = new_url
                    updated_references += 1
                
                # Variations
                for row in ProductVariation.query.filter_by(image_url=file_url).all():
                    row.image_url = new_url
                    updated_references += 1
                    
                # Descriptions (Text Replace)
                # This is expensive but necessary if we want to be thorough
                products = Product.query.filter(Product.description.contains(file_url)).all()
                for p in products:
                    p.description = p.description.replace(file_url, new_url)
                    updated_references += 1
                    
                # Delete old file
                try:
                    os.remove(full_path)
                except:
                    pass
    
    if converted_count > 0:
        db.session.commit()
        flash(f'Converted {converted_count} images to WebP and updated references.', 'success')
    else:
        flash('No images needed conversion.', 'info')
        
    return redirect(url_for('media.list_media'))
