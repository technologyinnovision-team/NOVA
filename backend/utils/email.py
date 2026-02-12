"""
Zoho Mail SMTP Email Utility for Fahad Styles

This module provides a robust email sending functionality using Zoho Mail SMTP.
It supports both SSL (port 465) and TLS (port 587) connections.

Zoho Mail SMTP Settings:
- Server: smtp.zoho.com (or smtp.zoho.in for India, smtp.zoho.eu for EU)
- SSL Port: 465 (uses SMTP_SSL)
- TLS Port: 587 (uses STARTTLS)
- Authentication: Required (email and password or app-specific password)
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
import logging
import os
import ssl
import traceback

# Configure logging
logger = logging.getLogger(__name__)


def get_smtp_config():
    """
    Retrieve SMTP configuration from database settings or environment variables.
    Database settings take priority over environment variables.
    
    Returns:
        dict: SMTP configuration containing all necessary settings
    """
    try:
        from models.setting import Setting
        
        def get_setting(key, default):
            """Helper to get setting with fallback"""
            try:
                val = Setting.get(key)
                return val if val is not None else default
            except Exception as e:
                logger.warning(f"Failed to get setting {key}: {e}")
                return default
        
        # Check if SMTP is enabled
        smtp_enabled = get_setting('smtp_enabled', False)
        if isinstance(smtp_enabled, str):
            smtp_enabled = smtp_enabled.lower() in ('true', '1', 'yes', 'on')
        
        # Use database settings with environment fallback
        config = {
            'enabled': smtp_enabled,
            'host': get_setting('smtp_host', os.environ.get('SMTP_SERVER', 'smtp.zoho.com')),
            'port': int(get_setting('smtp_port', os.environ.get('SMTP_PORT', 465))),
            'username': get_setting('smtp_username', os.environ.get('SMTP_USER', '')),
            'password': get_setting('smtp_password', os.environ.get('SMTP_PASS', '')),
            'from_email': get_setting('smtp_from_email', os.environ.get('SMTP_USER', '')),
            'from_name': get_setting('smtp_from_name', 'NOVA'),
            'encryption': get_setting('smtp_encryption', 'ssl'),  # 'ssl', 'tls', or 'none'
        }
        
        # Ensure from_email has a value
        if not config['from_email']:
            config['from_email'] = config['username']
        
        return config
    except Exception as e:
        logger.error(f"Error getting SMTP config from database: {e}")
        # Fallback to environment variables only
        return {
            'enabled': os.environ.get('SMTP_ENABLED', 'true').lower() == 'true',
            'host': os.environ.get('SMTP_SERVER', 'smtp.zoho.com'),
            'port': int(os.environ.get('SMTP_PORT', 465)),
            'username': os.environ.get('SMTP_USER', ''),
            'password': os.environ.get('SMTP_PASS', ''),
            'from_email': os.environ.get('SMTP_USER', ''),
            'from_name': os.environ.get('SMTP_FROM_NAME', 'NOVA'),
            'encryption': os.environ.get('SMTP_ENCRYPTION', 'ssl'),
        }


def create_smtp_connection(config):
    """
    Create and return an SMTP connection based on configuration.
    
    Zoho Mail supports:
    - SSL on port 465: Use SMTP_SSL
    - TLS on port 587: Use SMTP with STARTTLS
    
    Args:
        config: Dictionary containing SMTP configuration
        
    Returns:
        smtplib.SMTP or smtplib.SMTP_SSL: Connected and authenticated SMTP server
    """
    host = config['host']
    port = config['port']
    encryption = config.get('encryption', 'ssl')
    
    # Create SSL context for secure connections
    context = ssl.create_default_context()
    
    # Timeout for connection (30 seconds)
    timeout = 30
    
    logger.info(f"Connecting to SMTP server: {host}:{port} with encryption: {encryption}")
    
    if port == 465 or encryption == 'ssl':
        # Use SSL connection (recommended for Zoho)
        server = smtplib.SMTP_SSL(host, port, context=context, timeout=timeout)
    elif port == 587 or encryption == 'tls':
        # Use TLS connection with STARTTLS
        server = smtplib.SMTP(host, port, timeout=timeout)
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
    else:
        # Plain connection (not recommended)
        server = smtplib.SMTP(host, port, timeout=timeout)
        server.ehlo()
    
    # Enable debug output for troubleshooting (set to 0 for production)
    server.set_debuglevel(0)
    
    # Authenticate
    username = config['username']
    password = config['password']
    
    if username and password:
        logger.info(f"Authenticating with SMTP server as: {username}")
        server.login(username, password)
    else:
        raise ValueError("SMTP credentials not configured")
    
    return server


def send_email(to_email, subject, body, html=None):
    """
    Send an email using Zoho Mail SMTP.
    
    Args:
        to_email: Recipient email address (string or list of strings)
        subject: Email subject line
        body: Plain text body of the email
        html: Optional HTML body of the email
        
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    server = None
    
    try:
        # Get SMTP configuration
        config = get_smtp_config()
        
        # Check if SMTP is enabled
        if not config['enabled']:
            # Check if there are env credentials as fallback
            if config['username'] and config['password']:
                logger.info("SMTP disabled in settings but credentials available in env, proceeding with send")
            else:
                logger.warning("SMTP is disabled in settings. Email not sent.")
                logger.info(f"Would have sent email to {to_email} with subject: {subject}")
                return False
        
        # Validate credentials
        if not config['username'] or not config['password']:
            logger.warning("SMTP credentials not configured. Email not sent.")
            logger.info(f"Would have sent email to {to_email} with subject: {subject}")
            return False
        
        # Handle multiple recipients
        if isinstance(to_email, str):
            to_emails = [to_email]
        else:
            to_emails = list(to_email)
        
        # Filter out empty/invalid emails
        to_emails = [e.strip() for e in to_emails if e and e.strip()]
        
        if not to_emails:
            logger.error("No valid recipient email addresses provided")
            return False
        
        # Create message
        msg = MIMEMultipart('alternative')
        
        # Set From header with name (important for Zoho)
        from_name = config['from_name'] or 'NOVA'
        from_email = config['from_email']
        msg['From'] = formataddr((from_name, from_email))
        
        # Set To header
        msg['To'] = ', '.join(to_emails)
        
        # Set Subject
        msg['Subject'] = subject
        
        # Add Reply-To header (same as from)
        msg['Reply-To'] = from_email
        
        # Add plain text body
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # Add HTML body if provided
        if html:
            msg.attach(MIMEText(html, 'html', 'utf-8'))
        
        # Create connection and send
        server = create_smtp_connection(config)
        
        # Send to all recipients
        failed_recipients = []
        for recipient in to_emails:
            try:
                server.sendmail(from_email, recipient, msg.as_string())
                logger.info(f"Email sent successfully to {recipient}")
            except Exception as e:
                logger.error(f"Failed to send email to {recipient}: {e}")
                failed_recipients.append(recipient)
        
        # Close connection
        server.quit()
        
        if failed_recipients:
            logger.error(f"Email failed for some recipients: {failed_recipients}")
            return len(failed_recipients) < len(to_emails)  # Partial success
        
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP Authentication failed: {e}")
        logger.error("Check your Zoho Mail username and password. "
                    "If using 2FA, you need to create an App-Specific Password.")
        return False
    
    except smtplib.SMTPConnectError as e:
        logger.error(f"Failed to connect to SMTP server: {e}")
        logger.error("Check your firewall settings and ensure the SMTP port is not blocked.")
        return False
    
    except smtplib.SMTPServerDisconnected as e:
        logger.error(f"SMTP server disconnected unexpectedly: {e}")
        logger.error("This may be caused by antivirus software (e.g., Mail Shield feature). "
                    "Try disabling email scanning in your antivirus settings.")
        return False
    
    except smtplib.SMTPRecipientsRefused as e:
        logger.error(f"Recipient refused: {e}")
        return False
    
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error: {e}")
        return False
    
    except ConnectionResetError as e:
        error_msg = str(e)
        if "10054" in error_msg:
            logger.error(f"Connection forcibly closed: {e}")
            logger.error("This is often caused by Antivirus 'Mail Shield' (e.g., Avast, AVG) "
                        "blocking the SMTP connection. Try disabling Mail Shield temporarily.")
        else:
            logger.error(f"Connection reset: {e}")
        return False
    
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        logger.error(traceback.format_exc())
        return False
    
    finally:
        # Ensure connection is closed
        if server:
            try:
                server.quit()
            except:
                pass


def send_email_async(to_email, subject, body, html=None):
    """
    Send an email asynchronously in a separate thread.
    
    This is useful for not blocking the main request thread when sending emails.
    
    Args:
        to_email: Recipient email address
        subject: Email subject line
        body: Plain text body
        html: Optional HTML body
    """
    import threading
    
    def send_task():
        try:
            send_email(to_email, subject, body, html)
        except Exception as e:
            logger.error(f"Async email send failed: {e}")
    
    thread = threading.Thread(target=send_task, daemon=True)
    thread.start()
    logger.info(f"Email send thread started for {to_email}")
    return thread


def test_smtp_connection():
    """
    Test the SMTP connection with current settings.
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        config = get_smtp_config()
        
        if not config['username'] or not config['password']:
            return False, "SMTP credentials not configured"
        
        server = create_smtp_connection(config)
        server.quit()
        
        return True, f"Successfully connected to {config['host']}:{config['port']}"
    
    except smtplib.SMTPAuthenticationError:
        return False, "Authentication failed. Check username and password."
    
    except smtplib.SMTPConnectError as e:
        return False, f"Connection failed: {e}"
    
    except ConnectionResetError as e:
        if "10054" in str(e):
            return False, "Connection blocked. Check antivirus Mail Shield settings."
        return False, f"Connection reset: {e}"
    
    except Exception as e:
        return False, f"Error: {e}"


def send_test_email(to_email):
    """
    Send a test email to verify SMTP configuration.
    
    Args:
        to_email: Email address to send test to
        
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        subject = "Test Email from Fahad Styles"
        body = "This is a test email to verify your SMTP configuration is working correctly."
        html = """
        <div style="font-family: Arial, sans-serif; padding: 20px; max-width: 600px; margin: 0 auto;">
            <div style="background-color: #740c08; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
                <h1 style="color: #ffffff; margin: 0;">FAHAD STYLES</h1>
            </div>
            <div style="padding: 30px; background-color: #ffffff; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 8px 8px;">
                <h2 style="color: #333;">Email Test Successful! ✓</h2>
                <p style="color: #666; line-height: 1.6;">
                    Congratulations! Your SMTP configuration is working correctly.
                </p>
                <p style="color: #666; line-height: 1.6;">
                    This test email was sent from your Fahad Styles store to verify that 
                    order confirmations and notifications will be delivered successfully.
                </p>
                <div style="margin-top: 20px; padding: 15px; background-color: #f5f5f5; border-radius: 6px;">
                    <p style="margin: 0; color: #333; font-weight: bold;">SMTP Configuration Active</p>
                    <p style="margin: 5px 0 0; color: #666; font-size: 14px;">Your email system is ready to send order notifications.</p>
                </div>
            </div>
            <div style="text-align: center; padding: 20px; color: #999; font-size: 12px;">
                &copy; Fahad Styles. All rights reserved.
            </div>
        </div>
        """
        
        success = send_email(to_email, subject, body, html)
        
        if success:
            return True, f"Test email sent successfully to {to_email}"
        else:
            return False, "Failed to send test email. Check server logs for details."
    
    except Exception as e:
        return False, f"Error sending test email: {e}"
