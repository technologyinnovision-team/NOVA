from flask import current_app, url_for
import os
from werkzeug.utils import secure_filename
from datetime import datetime
import uuid
import shutil
from PIL import Image

def allowed_file(filename):
    """Check if file extension is allowed"""
    allowed = current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'webp'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed

def ensure_upload_directory(folder='products'):
    """Ensure upload directory exists"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    upload_base = os.path.join(base_dir, current_app.config.get('UPLOAD_FOLDER', 'uploads'))
    upload_dir = os.path.join(upload_base, folder)
    
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir, exist_ok=True)
    
    return upload_dir

def convert_to_webp(file_path, quality=85):
    """Convert an image file to WebP format"""
    try:
        with Image.open(file_path) as img:
            # Handle RGBA for PNG
            if img.mode in ('RGBA', 'LA'):
                background = Image.new(img.mode[:-1], img.size, (255, 255, 255))
                background.paste(img, img.split()[-1])
                img = background.convert('RGB')
            elif img.mode == 'P':
                img = img.convert('RGB')
                
            # Generate new path with .webp extension
            file_root, _ = os.path.splitext(file_path)
            new_path = f"{file_root}.webp"
            
            # Save as WebP
            img.save(new_path, 'WEBP', quality=quality)
            
            return new_path
    except Exception as e:
        print(f"Error converting to WebP: {e}")
        return file_path  # Return original if conversion fails

def upload_file_local(file, folder='products'):
    """Upload file to local storage and convert to WebP"""
    if not file or file.filename == '':
        return None
    
    if not allowed_file(file.filename):
        raise ValueError('File type not allowed')
    
    try:
        # Generate unique filename but keep original extension for now
        ext = file.filename.rsplit('.', 1)[1].lower()
        unique_id = uuid.uuid4()
        temp_filename = f"{unique_id}.{ext}"
        
        # Ensure directory exists
        upload_dir = ensure_upload_directory(folder)
        
        # Save original file temporarily
        temp_path = os.path.join(upload_dir, temp_filename)
        file.save(temp_path)
        
        # Convert to WebP
        # If it's already webp, just keep it, but we can re-save to ensure consistency/optimization if needed.
        # But for efficiency, if it is webp, maybe skipping is fine? 
        # Requirement says "Convert all images to webp", so let's convert everything to ensure uniform webp.
        
        webp_path = convert_to_webp(temp_path)
        
        # If conversion happened and created a new file, remove the old one (if extensions differ)
        if webp_path != temp_path:
            try:
                os.remove(temp_path)
            except:
                pass
        
        # Get the filename from the new path
        final_filename = os.path.basename(webp_path)
        
        # Generate URL path (relative to uploads folder)
        public_url = f"/uploads/{folder}/{final_filename}"
        
        return public_url
        
    except Exception as e:
        print(f"Error uploading file: {e}")
        raise

def delete_file_local(file_url):
    """Delete file from local storage"""
    try:
        # Extract path from URL
        # URL format: /uploads/folder/filename or full URL
        if file_url.startswith('/uploads/'):
            # Relative path
            file_path = file_url[1:]  # Remove leading /
        elif '/uploads/' in file_url:
            # Full URL, extract path
            parts = file_url.split('/uploads/')
            if len(parts) > 1:
                file_path = f"uploads/{parts[1]}"
            else:
                return False
        else:
            # Assume it's already a relative path
            file_path = file_url
        
        # Get absolute path
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_path = os.path.join(base_dir, file_path)
        
        # Check if file exists and delete
        if os.path.exists(full_path):
            os.remove(full_path)
            return True
        else:
            print(f"File not found: {full_path}")
            return False
        
    except Exception as e:
        print(f"Error deleting file: {e}")
        return False

def download_file_from_url(url, folder='products'):
    """Download file from URL, save to local storage, and convert to WebP"""
    import requests
    from io import BytesIO
    
    try:
        response = requests.get(url, timeout=30, stream=True)
        response.raise_for_status()
        
        # Check content type
        content_type = response.headers.get('Content-Type', '')
        if not content_type.startswith('image/'):
            raise ValueError('URL does not point to an image')
        
        # Get file extension from URL or content type
        ext = 'jpg'
        if '.' in url:
            ext = url.rsplit('.', 1)[1].lower().split('?')[0]
        elif 'jpeg' in content_type:
            ext = 'jpg'
        elif 'png' in content_type:
            ext = 'png'
        elif 'gif' in content_type:
            ext = 'gif'
        elif 'webp' in content_type:
            ext = 'webp'
        
        if ext not in current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'webp'}):
            ext = 'jpg'
        
        # Generate filename
        unique_id = uuid.uuid4()
        temp_filename = f"{unique_id}.{ext}"
        
        # Ensure directory exists
        upload_dir = ensure_upload_directory(folder)
        
        # Save temp file
        temp_path = os.path.join(upload_dir, temp_filename)
        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # Convert to WebP
        webp_path = convert_to_webp(temp_path)
        
        # Remove temp file if name changed
        if webp_path != temp_path:
            try:
                os.remove(temp_path)
            except:
                pass
                
        # Get final filename
        final_filename = os.path.basename(webp_path)
        
        # Generate URL path
        public_url = f"/uploads/{folder}/{final_filename}"
        
        return public_url
        
    except Exception as e:
        print(f"Error downloading and saving file: {e}")
        raise
