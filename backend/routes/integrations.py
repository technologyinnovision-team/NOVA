from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db
from models.integration import Integration
from utils.permissions import login_required

integrations = Blueprint('integrations', __name__, url_prefix='/admin/integrations')

@integrations.route('/config', methods=['GET', 'POST'])
@login_required
def config():
    """Integrations configuration - Head/Body/Footer codes and Direct & API integrations"""
    
    # Integration names for Direct & API integrations only
    direct_api_integrations = [
        'google_merchant_center',
        'microsoft_charity',
        'tiktok_catalog',
        'facebook_catalog',
        'pinterest_catalog'
    ]
    
    if request.method == 'POST':
        # Handle Head/Body/Footer codes
        header_code = request.form.get('header_code', '').strip()
        body_code = request.form.get('body_code', '').strip()
        footer_code = request.form.get('footer_code', '').strip()
        
        # Store in integration model with special keys
        for code_type, code_value in [('header', header_code), ('body', body_code), ('footer', footer_code)]:
            integration = Integration.query.filter_by(integration_name=f'custom_{code_type}_code').first()
            if not integration:
                integration = Integration(integration_name=f'custom_{code_type}_code', enabled=True, config={})
                db.session.add(integration)
            integration.config = {'code': code_value}
            integration.enabled = bool(code_value)
        
        # Handle Direct & API integrations
        for name in direct_api_integrations:
            integration = Integration.query.filter_by(integration_name=name).first()
            if not integration:
                integration = Integration(integration_name=name, enabled=False, config={})
                db.session.add(integration)
            
            integration.enabled = request.form.get(f'{name}_enabled') == 'on'
            
            # Set config based on integration type
            if name == 'google_merchant_center':
                integration.config = {
                    'merchant_id': request.form.get('gmc_merchant_id', ''),
                    'feed_url': request.form.get('gmc_feed_url', ''),
                    'access_token': request.form.get('gmc_access_token', '') if request.form.get('gmc_access_token') else integration.config.get('access_token', '')
                }
            elif name == 'microsoft_charity':
                integration.config = {}
            elif name == 'tiktok_catalog':
                integration.config = {
                    'catalog_id': request.form.get('tiktok_catalog_id', ''),
                    'access_token': request.form.get('tiktok_access_token', '') if request.form.get('tiktok_access_token') else integration.config.get('access_token', ''),
                    'app_id': request.form.get('tiktok_app_id', '')
                }
            elif name == 'facebook_catalog':
                integration.config = {
                    'catalog_id': request.form.get('facebook_catalog_id', ''),
                    'access_token': request.form.get('facebook_catalog_access_token', '') if request.form.get('facebook_catalog_access_token') else integration.config.get('access_token', ''),
                    'pixel_id': request.form.get('facebook_catalog_pixel_id', ''),
                    'business_manager_id': request.form.get('facebook_business_manager_id', '')
                }
            elif name == 'pinterest_catalog':
                integration.config = {
                    'catalog_id': request.form.get('pinterest_catalog_id', ''),
                    'access_token': request.form.get('pinterest_catalog_access_token', '') if request.form.get('pinterest_catalog_access_token') else integration.config.get('access_token', '')
                }
        
        db.session.commit()
        flash('Integrations updated successfully!', 'success')
        return redirect(url_for('integrations.config'))
    
    # Get Head/Body/Footer codes
    header_integration = Integration.query.filter_by(integration_name='custom_header_code').first()
    body_integration = Integration.query.filter_by(integration_name='custom_body_code').first()
    footer_integration = Integration.query.filter_by(integration_name='custom_footer_code').first()
    
    header_code = header_integration.config.get('code', '') if header_integration and header_integration.config else ''
    body_code = body_integration.config.get('code', '') if body_integration and body_integration.config else ''
    footer_code = footer_integration.config.get('code', '') if footer_integration and footer_integration.config else ''
    
    # Get Direct & API integrations
    integrations_dict = {}
    for name in direct_api_integrations:
        integration = Integration.query.filter_by(integration_name=name).first()
        if not integration:
            integration = Integration(integration_name=name, enabled=False, config={})
            db.session.add(integration)
    
    db.session.commit()
    
    for name in direct_api_integrations:
        integrations_dict[name] = Integration.query.filter_by(integration_name=name).first()
    
    return render_template('integrations/config.html', 
                         header_code=header_code,
                         body_code=body_code,
                         footer_code=footer_code,
                         integrations=integrations_dict)
