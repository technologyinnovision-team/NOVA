
from flask import Blueprint, render_template, request, jsonify, send_file, current_app, flash, redirect, url_for
from utils.permissions import login_required, require_permission
from utils.backup import BackupService
import os

backups = Blueprint('backups', __name__, url_prefix='/admin/backups')

@backups.route('/')
@login_required
@require_permission('settings')
def index():
    """Render backups page"""
    return render_template('dashboard/backups.html')

@backups.route('/create', methods=['POST'])
@login_required
@require_permission('settings')
def create():
    """Create a new backup"""
    try:
        data = request.json
        include_db = data.get('database', False)
        include_media = data.get('media', False)
        
        if not include_db and not include_media:
            return jsonify({'success': False, 'message': 'Please select at least one option to export.'}), 400
            
        zip_path = BackupService.create_backup(include_db=include_db, include_media=include_media)
        filename = os.path.basename(zip_path)
        
        return jsonify({
            'success': True,
            'message': 'Backup created successfully!',
            'download_url': url_for('backups.download', filename=filename)
        })
        
    except Exception as e:
        current_app.logger.error(f"Backup creation failed: {str(e)}")
        return jsonify({'success': False, 'message': f'Backup failed: {str(e)}'}), 500

@backups.route('/download/<filename>')
@login_required
@require_permission('settings')
def download(filename):
    """Download a backup file"""
    try:
        backup_dir = os.path.join(current_app.root_path, 'backups')
        return send_file(os.path.join(backup_dir, filename), as_attachment=True)
    except Exception as e:
        flash(f'Error downloading file: {str(e)}', 'error')
        return redirect(url_for('backups.index'))
