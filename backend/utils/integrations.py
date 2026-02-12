"""
Helper functions for extracting and generating integration codes
"""
from models.integration import Integration


def get_integration_codes():
    """
    Extract custom codes from integrations (for header/body/footer sections).
    Returns a dict with 'header', 'body', 'footer' keys containing code strings.
    """
    codes = {
        'header': '',
        'body': '',
        'footer': ''
    }
    
    # Get custom code integrations
    header_integration = Integration.query.filter_by(integration_name='custom_header_code').first()
    body_integration = Integration.query.filter_by(integration_name='custom_body_code').first()
    footer_integration = Integration.query.filter_by(integration_name='custom_footer_code').first()
    
    if header_integration and header_integration.enabled and header_integration.config:
        codes['header'] = header_integration.config.get('code', '').strip()
    
    if body_integration and body_integration.enabled and body_integration.config:
        codes['body'] = body_integration.config.get('code', '').strip()
    
    if footer_integration and footer_integration.enabled and footer_integration.config:
        codes['footer'] = footer_integration.config.get('code', '').strip()
    
    return codes


def get_individual_integration_codes():
    """
    Extract individual integration codes for template variables.
    Returns a dict with individual codes (for backward compatibility).
    This function is kept for compatibility but returns empty dict since
    we're using only custom code injection now.
    """
    codes = {}
    
    # This function is kept for backward compatibility
    # All codes are now handled via get_integration_codes() for header/body/footer
    
    return codes
