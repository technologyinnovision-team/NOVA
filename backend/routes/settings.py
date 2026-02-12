from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db
from models.setting import Setting
from utils.permissions import login_required
from decimal import Decimal

settings = Blueprint('settings', __name__, url_prefix='/admin/settings')

@settings.route('/general', methods=['GET', 'POST'])
@login_required
def general():
    """General settings page - Tax, SMTP, Admin Emails"""
    if request.method == 'POST':
        try:
            # Tax Settings
            tax_enabled = request.form.get('tax_enabled') == 'on'
            tax_rate = request.form.get('tax_rate', '0')
            tax_calculation_method = request.form.get('tax_calculation_method', 'per_item')
            tax_display = request.form.get('tax_display', 'exclusive')
            
            Setting.set('tax_enabled', tax_enabled, 'boolean', 'tax', 'Enable tax calculation')
            Setting.set('tax_rate', float(tax_rate) if tax_rate else 0, 'number', 'tax', 'Default tax rate percentage')
            Setting.set('tax_calculation_method', tax_calculation_method, 'string', 'tax', 'Tax calculation method')
            Setting.set('tax_display', tax_display, 'string', 'tax', 'Tax display method')
            
            # SMTP Settings
            smtp_enabled = request.form.get('smtp_enabled') == 'on'
            smtp_host = request.form.get('smtp_host', '').strip()
            smtp_port = request.form.get('smtp_port', '587')
            smtp_username = request.form.get('smtp_username', '').strip()
            smtp_password = request.form.get('smtp_password', '').strip()
            smtp_encryption = request.form.get('smtp_encryption', 'tls')
            smtp_from_email = request.form.get('smtp_from_email', '').strip()
            smtp_from_name = request.form.get('smtp_from_name', '').strip()
            
            Setting.set('smtp_enabled', smtp_enabled, 'boolean', 'smtp', 'Enable SMTP email')
            Setting.set('smtp_host', smtp_host, 'string', 'smtp', 'SMTP server host')
            Setting.set('smtp_port', int(smtp_port) if smtp_port else 587, 'number', 'smtp', 'SMTP server port')
            Setting.set('smtp_username', smtp_username, 'string', 'smtp', 'SMTP username')
            # Only update password if provided (to avoid clearing existing password)
            if smtp_password:
                Setting.set('smtp_password', smtp_password, 'string', 'smtp', 'SMTP password')
            Setting.set('smtp_encryption', smtp_encryption, 'string', 'smtp', 'SMTP encryption (tls/ssl/none)')
            Setting.set('smtp_from_email', smtp_from_email, 'string', 'smtp', 'From email address')
            Setting.set('smtp_from_name', smtp_from_name, 'string', 'smtp', 'From name')
            
            # Admin Emails
            admin_primary_email = request.form.get('admin_primary_email', '').strip()
            admin_notification_emails = request.form.get('admin_notification_emails', '').strip()
            
            Setting.set('admin_primary_email', admin_primary_email, 'string', 'admin_emails', 'Primary admin email')
            Setting.set('admin_notification_emails', admin_notification_emails, 'string', 'admin_emails', 'Notification emails (comma-separated)')

            # GitHub Update Settings
            github_token = request.form.get('github_token', '').strip()
            repo_owner = request.form.get('repo_owner', '').strip()
            repo_name = request.form.get('repo_name', '').strip()

            if github_token: # Only update if provided to allow keeping existing
                Setting.set('github_token', github_token, 'string', 'updates', 'GitHub Access Token')
            Setting.set('repo_owner', repo_owner, 'string', 'updates', 'GitHub Repository Owner')
            Setting.set('repo_name', repo_name, 'string', 'updates', 'GitHub Repository Name')
            
            flash('Settings updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating settings: {str(e)}', 'error')
            print(f"Error: {e}")
        
        return redirect(url_for('settings.general'))
    
    # Get current settings
    tax_settings = {
        'enabled': Setting.get('tax_enabled', False),
        'rate': Setting.get('tax_rate', 0),
        'calculation_method': Setting.get('tax_calculation_method', 'per_item'),
        'display': Setting.get('tax_display', 'exclusive'),
    }
    
    smtp_settings = {
        'enabled': Setting.get('smtp_enabled', False),
        'host': Setting.get('smtp_host', ''),
        'port': Setting.get('smtp_port', 587),
        'username': Setting.get('smtp_username', ''),
        'password': Setting.get('smtp_password', ''),  # Will show as empty for security
        'encryption': Setting.get('smtp_encryption', 'tls'),
        'from_email': Setting.get('smtp_from_email', ''),
        'from_name': Setting.get('smtp_from_name', ''),
    }
    
    admin_settings = {
        'primary_email': Setting.get('admin_primary_email', ''),
        'notification_emails': Setting.get('admin_notification_emails', ''),
    }

    update_settings = {
        'github_token': Setting.get('github_token', ''),
        'repo_owner': Setting.get('repo_owner', ''),
        'repo_name': Setting.get('repo_name', ''),
    }
    
    return render_template('settings/general.html', 
                         tax_settings=tax_settings,
                         smtp_settings=smtp_settings,
                         admin_settings=admin_settings,
                         update_settings=update_settings)
    
    return render_template('settings/general.html', 
                         tax_settings=tax_settings,
                         smtp_settings=smtp_settings,
                         admin_settings=admin_settings)


@settings.route('/test-smtp-connection', methods=['POST'])
@login_required
def test_smtp_connection():
    """Test SMTP connection without sending email"""
    from flask import jsonify
    from utils.email import test_smtp_connection as do_test
    
    try:
        success, message = do_test()
        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@settings.route('/send-test-email', methods=['POST'])
@login_required
def send_test_email_route():
    """Send a test email to verify SMTP configuration"""
    from flask import jsonify
    from utils.email import send_test_email
    
    try:
        to_email = request.form.get('test_email', '').strip()
        
        if not to_email:
            # Fallback to admin primary email or from_email
            to_email = Setting.get('admin_primary_email', '')
            if not to_email:
                to_email = Setting.get('smtp_from_email', '')
        
        if not to_email:
            return jsonify({
                'success': False,
                'message': 'Please provide an email address to send the test to'
            }), 400
        
        success, message = send_test_email(to_email)
        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

