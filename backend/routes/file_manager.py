from flask import Blueprint, render_template, request, jsonify, current_app, send_from_directory
from utils.permissions import login_required, require_role
import os
import shutil
from werkzeug.utils import secure_filename

file_manager = Blueprint('file_manager', __name__, url_prefix='/admin/file-manager')

def get_build_dir():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, 'build')

def is_safe_path(path):
    """Ensure path is within build directory"""
    build_dir = get_build_dir()
    # Resolve absolute path
    abs_path = os.path.abspath(path)
    # Check if it starts with build_dir
    return os.path.commonpath([build_dir, abs_path]) == build_dir

@file_manager.route('/')
@login_required
def index():
    """Render File Manager Interface"""
    return render_template('file_manager/index.html')

@file_manager.route('/api/list')
@login_required
def list_files():
    """List files in a directory"""
    req_path = request.args.get('path', '')
    
    # Normalize path
    req_path = req_path.strip('/')
    build_dir = get_build_dir()
    target_dir = os.path.join(build_dir, req_path)
    
    if not is_safe_path(target_dir):
        return jsonify({'error': 'Invalid path'}), 403
        
    if not os.path.exists(target_dir):
        return jsonify({'error': 'Directory not found'}), 404
        
    items = []
    try:
        # Get directories first, then files
        with os.scandir(target_dir) as entries:
            for entry in entries:
                is_dir = entry.is_dir()
                size = entry.stat().st_size if not is_dir else 0
                modified = entry.stat().st_mtime
                
                items.append({
                    'name': entry.name,
                    'is_dir': is_dir,
                    'size': size,
                    'modified': modified,
                    'path': os.path.join(req_path, entry.name).replace('\\', '/')
                })
                
        # Sort: directories first, then by name
        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        
        return jsonify({
            'current_path': req_path,
            'items': items
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@file_manager.route('/api/create-folder', methods=['POST'])
@login_required
def create_folder():
    """Create a new folder"""
    req_path = request.json.get('path', '')
    folder_name = request.json.get('name', '')
    
    if not folder_name:
        return jsonify({'error': 'Folder name is required'}), 400
        
    # Sanitize folder name
    folder_name = secure_filename(folder_name)
    
    build_dir = get_build_dir()
    target_path = os.path.join(build_dir, req_path, folder_name)
    
    if not is_safe_path(target_path):
        return jsonify({'error': 'Invalid path'}), 403
        
    try:
        os.makedirs(target_path, exist_ok=False)
        return jsonify({'success': True, 'message': 'Folder created'})
    except FileExistsError:
        return jsonify({'error': 'Folder already exists'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@file_manager.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    """Upload files"""
    if 'files[]' not in request.files:
        return jsonify({'error': 'No files uploaded'}), 400
        
    files = request.files.getlist('files[]')
    req_path = request.form.get('path', '')
    
    build_dir = get_build_dir()
    target_dir = os.path.join(build_dir, req_path)
    
    if not is_safe_path(target_dir):
        return jsonify({'error': 'Invalid path'}), 403
        
    uploaded_count = 0
    errors = []
    
    for file in files:
        if file.filename == '':
            continue
            
        filename = secure_filename(file.filename)
        destination = os.path.join(target_dir, filename)
        
        try:
            file.save(destination)
            uploaded_count += 1
        except Exception as e:
            errors.append(f"{file.filename}: {str(e)}")
            
    return jsonify({
        'success': True,
        'count': uploaded_count,
        'errors': errors
    })

@file_manager.route('/api/delete', methods=['POST'])
@login_required
@require_role('Super Admin') # Extra safety
def delete_item():
    """Delete a file or directory"""
    req_path = request.json.get('path', '')
    
    if not req_path:
        return jsonify({'error': 'Path required'}), 400
        
    build_dir = get_build_dir()
    target_path = os.path.join(build_dir, req_path)
    
    if not is_safe_path(target_path):
        return jsonify({'error': 'Invalid path'}), 403
        
    # Protect root build dir
    if target_path == build_dir:
         return jsonify({'error': 'Cannot delete root directory'}), 403
         
    try:
        if os.path.isfile(target_path):
            os.remove(target_path)
        elif os.path.isdir(target_path):
            shutil.rmtree(target_path)
        else:
            return jsonify({'error': 'Item not found'}), 404
            
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@file_manager.route('/api/download')
@login_required
def download_file():
    """Download a file"""
    req_path = request.args.get('path', '')
    
    build_dir = get_build_dir()
    target_path = os.path.join(build_dir, req_path)
    
    if not is_safe_path(target_path):
        return jsonify({'error': 'Invalid path'}), 403
        
    if not os.path.isfile(target_path):
        return jsonify({'error': 'File not found'}), 404
        
    directory = os.path.dirname(target_path)
    filename = os.path.basename(target_path)
    
    return send_from_directory(directory, filename, as_attachment=True)

# --- Advanced Features ---

@file_manager.route('/api/create-file', methods=['POST'])
@login_required
def create_file():
    """Create a new file"""
    req_path = request.json.get('path', '')
    filename = request.json.get('name', '')
    
    if not filename:
        return jsonify({'error': 'Filename is required'}), 400
        
    build_dir = get_build_dir()
    target_path = os.path.join(build_dir, req_path, filename)
    
    if not is_safe_path(target_path):
        return jsonify({'error': 'Invalid path'}), 403
        
    try:
        if os.path.exists(target_path):
            return jsonify({'error': 'File already exists'}), 400
            
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write('') # Create empty file
            
        return jsonify({'success': True, 'message': 'File created'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@file_manager.route('/api/get-content', methods=['GET'])
@login_required
def get_content():
    """Get file content for editing"""
    req_path = request.args.get('path', '')
    
    build_dir = get_build_dir()
    target_path = os.path.join(build_dir, req_path)
    
    if not is_safe_path(target_path):
        return jsonify({'error': 'Invalid path'}), 403
        
    if not os.path.isfile(target_path):
        return jsonify({'error': 'File not found'}), 404
        
    try:
        # Check file size - limit editing to 2MB
        if os.path.getsize(target_path) > 2 * 1024 * 1024:
            return jsonify({'error': 'File too large to edit'}), 400
            
        with open(target_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        return jsonify({'content': content})
    except UnicodeDecodeError:
        return jsonify({'error': 'Cannot edit binary files'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@file_manager.route('/api/save-content', methods=['POST'])
@login_required
def save_content():
    """Save file content"""
    req_path = request.json.get('path', '')
    content = request.json.get('content', '')
    
    build_dir = get_build_dir()
    target_path = os.path.join(build_dir, req_path)
    
    if not is_safe_path(target_path):
        return jsonify({'error': 'Invalid path'}), 403
        
    if not os.path.exists(target_path):
        return jsonify({'error': 'File not found'}), 404
        
    try:
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@file_manager.route('/api/compress', methods=['POST'])
@login_required
def compress_files():
    """Compress selected files/folders"""
    import zipfile
    
    req_path = request.json.get('path', '') # Current directory
    items = request.json.get('items', []) # List of filenames in current directory
    archive_name = request.json.get('name', 'archive')
    
    if not items:
        return jsonify({'error': 'No items selected'}), 400
        
    build_dir = get_build_dir()
    base_path = os.path.join(build_dir, req_path)
    
    if not is_safe_path(base_path):
        return jsonify({'error': 'Invalid path'}), 403
        
    # Ensure archive name ends with .zip
    if not archive_name.lower().endswith('.zip'):
        archive_name += '.zip'
        
    zip_path = os.path.join(base_path, archive_name)
    
    if not is_safe_path(zip_path):
        return jsonify({'error': 'Invalid archive path'}), 403
        
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for item in items:
                item_path = os.path.join(base_path, item)
                
                if not is_safe_path(item_path) or not os.path.exists(item_path):
                    continue
                    
                if os.path.isfile(item_path):
                    zipf.write(item_path, item)
                elif os.path.isdir(item_path):
                    for root, dirs, files in os.walk(item_path):
                        for file in files:
                            file_full_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_full_path, base_path)
                            zipf.write(file_full_path, arcname)
                            
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@file_manager.route('/api/extract', methods=['POST'])
@login_required
def extract_file():
    """Extract a zip file"""
    import zipfile
    
    req_path = request.json.get('path', '') # Path to the zip file relative to build dir
    
    if not req_path:
        return jsonify({'error': 'Path required'}), 400
        
    build_dir = get_build_dir()
    zip_path = os.path.join(build_dir, req_path)
    
    if not is_safe_path(zip_path):
        return jsonify({'error': 'Invalid path'}), 403
        
    if not zipfile.is_zipfile(zip_path):
        return jsonify({'error': 'Not a valid zip file'}), 400
        
    # Extract to the same directory as the zip file
    extract_to = os.path.dirname(zip_path)
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            # Security check: ensure extraction doesn't go outside
            for member in zipf.namelist():
                # Block absolute paths and ..
                if os.path.isabs(member) or '..' in member:
                    continue
                    
                target_path = os.path.join(extract_to, member)
                if not is_safe_path(target_path):
                    continue
                    
                zipf.extract(member, extract_to)
                
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
