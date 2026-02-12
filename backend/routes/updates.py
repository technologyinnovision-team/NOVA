
from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for, flash
from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for, flash, Response, stream_with_context
from utils.permissions import login_required, require_role
from utils.updater import GitReleaseManager, SystemManager
from config import Config
from models.setting import Setting
import os
import threading
import time
import json

updates_bp = Blueprint('updates', __name__, url_prefix='/admin/updates')

# Global state for update process
UPDATE_LOGS = []
UPDATE_STATUS = {
    'running': False,
    'error': None
}

@updates_bp.route('/')
@login_required
@require_role('Super Admin')
def index():
    # Only Super Admins can manage updates
    current_version = Config.VERSION
    
    # Initialize managers
    # Get config from database
    token = Setting.get('github_token')
    repo_owner = Setting.get('repo_owner')
    repo_name = Setting.get('repo_name')
    
    latest_release = None
    error = None
    
    # helper to init manager
    def get_git_manager():
        if token and repo_owner and repo_name:
             return GitReleaseManager(repo_owner, repo_name, token)
        # Check env fallback
        env_token = current_app.config.get('GITHUB_TOKEN')
        env_owner = current_app.config.get('REPO_OWNER')
        env_name = current_app.config.get('REPO_NAME')
        if env_token and env_owner and env_name:
             return GitReleaseManager(env_owner, env_name, env_token)
        return None

    try:
        manager = get_git_manager()
        if manager:
            latest_release = manager.check_updates(current_version)
    except Exception as e:
        error = str(e)
        if not error: # If get_git_manager returned None and no exception
             error = "GitHub configuration missing. Please configure in Settings -> General."

    # Check for rollback availability (simplified - just check if backup exists)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys_manager = SystemManager(base_dir)
    
    rollback_available = sys_manager.has_backup()
    previous_version = sys_manager.get_backup_version() if rollback_available else None

    return render_template('admin/updates.html', 
                           current_version=current_version, 
                           latest_release=latest_release,
                           error=error,
                           rollback_available=rollback_available,
                           previous_version=previous_version,
                           update_running=UPDATE_STATUS['running'])

@updates_bp.route('/stream-logs')
@login_required
@require_role('Super Admin')
def stream_logs():
    def generate():
        last_index = 0
        while UPDATE_STATUS['running'] or last_index < len(UPDATE_LOGS):
            # Send new logs
            while last_index < len(UPDATE_LOGS):
                log_message = UPDATE_LOGS[last_index]
                yield f"data: {json.dumps({'message': log_message})}\n\n"
                last_index += 1
            
            if not UPDATE_STATUS['running'] and last_index >= len(UPDATE_LOGS):
                # Update finished
                if UPDATE_STATUS['error']:
                     yield f"data: {json.dumps({'type': 'error', 'message': UPDATE_STATUS['error']})}\n\n"
                else:
                     yield f"data: {json.dumps({'type': 'done', 'message': 'Update completed.'})}\n\n"
                break
                
            time.sleep(0.5)

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@updates_bp.route('/install', methods=['POST'])
@login_required
@require_role('Super Admin')
def install_update():
    if UPDATE_STATUS['running']:
        flash("An update is already in progress.", "warning")
        return redirect(url_for('updates.index'))

    version = request.form.get('version')
    asset_url = request.form.get('asset_url')
    
    if not version or not asset_url:
        flash("Invalid update request.", "error")
        return redirect(url_for('updates.index'))
        
    # Run update in background thread to avoid timeout
    # Note: In a real production app, use Celery or RQ
    thread = threading.Thread(target=run_update_process, args=(
        current_app._get_current_object(), version, asset_url
    ))
    thread.start()
    
    flash(f"Update to v{version} started. Logs will appear below.", "info")
    return redirect(url_for('updates.index'))

def run_update_process(app, version, asset_url):
    global UPDATE_LOGS, UPDATE_STATUS
    
    # Reset state
    UPDATE_LOGS = []
    UPDATE_STATUS['running'] = True
    UPDATE_STATUS['error'] = None
    
    def logger(msg):
        print(msg) # Keep stdout for server logs
        UPDATE_LOGS.append(msg)
        
    with app.app_context():
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
            # Get config from DB first, then Env
            token = Setting.get('github_token') or app.config.get('GITHUB_TOKEN')
            repo_owner = Setting.get('repo_owner') or app.config.get('REPO_OWNER')
            repo_name = Setting.get('repo_name') or app.config.get('REPO_NAME')
            
            git_manager = GitReleaseManager(repo_owner, repo_name, token, logger=logger)
            sys_manager = SystemManager(base_dir, logger=logger)
            
            # 1. Create Backup
            logger("Creating backup of current version...")
            sys_manager.create_backup()
            
            # 2. Download
            logger(f"Downloading update {version}...")
            zip_path = os.path.join(base_dir, f".temp_update_{version}.zip")
            git_manager.download_release(asset_url, zip_path)
            
            # 3. Extract directly to backend folder
            logger(f"Extracting update {version} to backend folder...")
            sys_manager.extract_release(zip_path)
            
            # Clean up zip file
            if os.path.exists(zip_path):
                os.remove(zip_path)
            
            # 4. Run Migrations
            logger("Running database migrations...")
            sys_manager.run_migrations()
            
            # 5. Update config.py VERSION
            logger(f"Updating version in config.py...")
            sys_manager.update_config_version(version)
            
            logger("Update completed successfully. Restarting services...")
            sys_manager.restart_services()
            
        except Exception as e:
            logger(f"Update failed: {e}")
            logger("Rolling back to previous version...")
            try:
                sys_manager.restore_from_backup()
                logger("Rollback completed. System restored to previous state.")
            except Exception as rollback_error:
                logger(f"Rollback failed: {rollback_error}")
            UPDATE_STATUS['error'] = str(e)
        finally:
            UPDATE_STATUS['running'] = False


@updates_bp.route('/rollback', methods=['POST'])
@login_required
@require_role('Super Admin')
def rollback():
    """Simple rollback that restores from the backup folder"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys_manager = SystemManager(base_dir)
    
    if not sys_manager.has_backup():
        flash("No backup available for rollback.", "error")
        return redirect(url_for('updates.index'))
    
    try:
        # Restore files from backup
        sys_manager.restore_from_backup()
        
        # Restart services
        sys_manager.restart_services()
        
        previous_version = sys_manager.get_backup_version()
        flash(f"Successfully rolled back to version {previous_version}. The system is restarting.", "success")
    except Exception as e:
        flash(f"Rollback failed: {str(e)}", "error")
    
    return redirect(url_for('updates.index'))
