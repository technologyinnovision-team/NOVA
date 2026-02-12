from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db
from models.payment import PaymentGateway
from utils.permissions import login_required
from sqlalchemy.orm.attributes import flag_modified

payments = Blueprint('payments', __name__, url_prefix='/admin/payments')

@payments.route('/gateways', methods=['GET', 'POST'])
@login_required
def gateways():
    """Payment gateway configuration"""
    if request.method == 'POST':
        try:
            # Update Stripe
            stripe = PaymentGateway.query.filter_by(gateway_name='stripe').first()
            if not stripe:
                stripe = PaymentGateway(gateway_name='stripe', enabled=False, config={})
                db.session.add(stripe)
            
            # Explicit boolean conversion - handle checkbox state correctly
            stripe_enabled_value = request.form.get('stripe_enabled')
            stripe.enabled = bool(stripe_enabled_value == 'on')
            
            # Debug: Log the values
            print(f"DEBUG: Stripe enabled checkbox value: {stripe_enabled_value}, Converted to: {stripe.enabled}, Type: {type(stripe.enabled)}")
            
            # Preserve existing config and encrypted keys
            # IMPORTANT: Get existing config BEFORE creating new dict to preserve encrypted keys
            existing_config = dict(stripe.config) if stripe.config else {}
            
            if not stripe.config:
                stripe.config = {}
            else:
                stripe.config = dict(stripe.config)
            
            # Handle secret key - only update if new value provided
            secret_key_input = request.form.get('stripe_secret_key', '').strip()
            
            if secret_key_input:
                try:
                    stripe.set_encrypted_key('secret_key', secret_key_input)
                except Exception as e:
                    print(f"Error setting encrypted key: {e}")
                    import traceback
                    traceback.print_exc()
                
                stripe.config['secret_key'] = secret_key_input
            else:
                # Preserve existing encrypted key - this is critical!
                if 'secret_key_encrypted' in existing_config:
                    stripe.config['secret_key_encrypted'] = existing_config['secret_key_encrypted']
                # Don't restore plain text secret_key - it should only be set when explicitly provided
                # The encrypted version is what matters for persistence
            
            # Update publishable key with validation
            publishable_key = request.form.get('stripe_publishable_key', '').strip()
            if publishable_key:
                if not publishable_key.startswith(('pk_test_', 'pk_live_')):
                    flash('Invalid Stripe publishable key format. Must start with pk_test_ or pk_live_', 'error')
                    db.session.rollback()
                    return redirect(url_for('payments.gateways'))
                stripe.config['publishable_key'] = publishable_key
            elif 'publishable_key' in existing_config:
                # Preserve existing publishable key if not provided
                stripe.config['publishable_key'] = existing_config['publishable_key']
            
            stripe.config['mode'] = request.form.get('stripe_mode', stripe.config.get('mode', 'test'))
            
            # Apple Pay & Google Pay settings
            stripe.config['apple_pay_enabled'] = bool(request.form.get('stripe_apple_pay_enabled') == 'on')
            stripe.config['google_pay_enabled'] = bool(request.form.get('stripe_google_pay_enabled') == 'on')
            
            flag_modified(stripe, 'config')
            
            # Update PayPal
            paypal = PaymentGateway.query.filter_by(gateway_name='paypal').first()
            if not paypal:
                paypal = PaymentGateway(gateway_name='paypal', enabled=False, config={})
                db.session.add(paypal)
            
            # Explicit boolean conversion for PayPal
            paypal_enabled_value = request.form.get('paypal_enabled')
            paypal.enabled = bool(paypal_enabled_value == 'on')
            
            # Debug: Log the values
            print(f"DEBUG: PayPal enabled checkbox value: {paypal_enabled_value}, Converted to: {paypal.enabled}, Type: {type(paypal.enabled)}")
            
            # Preserve PayPal config
            # IMPORTANT: Get existing config BEFORE creating new dict to preserve encrypted keys
            paypal_existing = dict(paypal.config) if paypal.config else {}
            
            if not paypal.config:
                paypal.config = {}
            else:
                paypal.config = dict(paypal.config)
            
            paypal_secret_input = request.form.get('paypal_secret', '').strip()
            if paypal_secret_input:
                paypal.set_encrypted_key('secret', paypal_secret_input)
                paypal.config['secret'] = paypal_secret_input
            else:
                # Preserve existing encrypted key - this is critical!
                if 'secret_encrypted' in paypal_existing:
                    paypal.config['secret_encrypted'] = paypal_existing['secret_encrypted']
                # Don't restore plain text secret - it should only be set when explicitly provided
                # The encrypted version is what matters for persistence
            
            # Handle client_id - preserve if not provided
            paypal_client_id = request.form.get('paypal_client_id', '').strip()
            if paypal_client_id:
                paypal.config['client_id'] = paypal_client_id
            elif 'client_id' in paypal_existing:
                # Preserve existing client_id if not provided
                paypal.config['client_id'] = paypal_existing['client_id']
            
            paypal.config['mode'] = request.form.get('paypal_mode', paypal.config.get('mode', 'test'))
            
            flag_modified(paypal, 'config')
            
            # Update COD (Cash on Delivery)
            cod = PaymentGateway.query.filter_by(gateway_name='cod').first()
            if not cod:
                cod = PaymentGateway(gateway_name='cod', enabled=False, config={})
                db.session.add(cod)
            
            cod_enabled_value = request.form.get('cod_enabled')
            cod.enabled = bool(cod_enabled_value == 'on')
            
            if not cod.config:
                cod.config = {}
                
            flag_modified(cod, 'config')
            
            # Update Bank Transfer
            bank = PaymentGateway.query.filter_by(gateway_name='bank_transfer').first()
            if not bank:
                bank = PaymentGateway(gateway_name='bank_transfer', enabled=False, config={})
                db.session.add(bank)
                
            bank_enabled_value = request.form.get('bank_enabled')
            bank.enabled = bool(bank_enabled_value == 'on')
            
            if not bank.config:
                bank.config = {}
            else:
                bank.config = dict(bank.config)
                
            # Update bank details
            bank.config['bank_name'] = request.form.get('bank_name', '').strip()
            bank.config['account_title'] = request.form.get('bank_account_title', '').strip()
            bank.config['account_number'] = request.form.get('bank_account_number', '').strip()
            bank.config['iban'] = request.form.get('bank_iban', '').strip()
            bank.config['instructions'] = request.form.get('bank_instructions', '').strip()
            
            flag_modified(bank, 'config')
            
            # Commit changes
            db.session.commit()
            
            # Force fresh query after commit
            db.session.expire_all()
            db.session.refresh(stripe)
            db.session.refresh(paypal)
            
            # Debug: Verify saved values
            print(f"DEBUG: After commit - Stripe enabled: {stripe.enabled}, Type: {type(stripe.enabled)}")
            print(f"DEBUG: After commit - PayPal enabled: {paypal.enabled}, Type: {type(paypal.enabled)}")
            
            flash('Payment gateways updated successfully!', 'success')
            
        except Exception as e:
            db.session.rollback()
            print(f"Error updating payment gateways: {e}")
            import traceback
            traceback.print_exc()
            flash(f'Error updating payment gateways: {str(e)}', 'error')
        
        return redirect(url_for('payments.gateways'))
    
    # GET request - always get fresh data
    db.session.expire_all()
    
    stripe = PaymentGateway.query.filter_by(gateway_name='stripe').first()
    paypal = PaymentGateway.query.filter_by(gateway_name='paypal').first()
    cod = PaymentGateway.query.filter_by(gateway_name='cod').first()
    bank = PaymentGateway.query.filter_by(gateway_name='bank_transfer').first()
    
    # Ensure boolean values (not None or string)
    if stripe:
        stripe.enabled = bool(stripe.enabled) if stripe.enabled is not None else False
    if paypal:
        paypal.enabled = bool(paypal.enabled) if paypal.enabled is not None else False
    if cod:
        cod.enabled = bool(cod.enabled) if cod.enabled is not None else False
    if bank:
        bank.enabled = bool(bank.enabled) if bank.enabled is not None else False
    
    # Debug: Log values being sent to template
    print(f"DEBUG: Template render - Stripe enabled: {stripe.enabled if stripe else None}, Type: {type(stripe.enabled) if stripe else None}")
    print(f"DEBUG: Template render - PayPal enabled: {paypal.enabled if paypal else None}, Type: {type(paypal.enabled) if paypal else None}")
    print(f"DEBUG: Template render - COD enabled: {cod.enabled if cod else None}, Type: {type(cod.enabled) if cod else None}")
    
    return render_template('payments/gateways.html', stripe=stripe, paypal=paypal, cod=cod, bank=bank)
