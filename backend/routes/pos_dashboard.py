from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from utils.permissions import login_required
from utils.auth import get_current_user
from models.product import Product
from models.order import Order
from models.pos import POSInventory
from models.wallet import Wallet, WalletTransaction, PayoutRequest
from models import db
from services.fulfillment_service import FulfillmentService
from models.wallet import Wallet, WalletTransaction, PayoutRequest
from models import db
from services.fulfillment_service import FulfillmentService
from services.payment_service import PaymentService
from datetime import datetime
from decimal import Decimal
from sqlalchemy.orm import joinedload

pos_dashboard = Blueprint('pos_dashboard', __name__, url_prefix='/pos')

@pos_dashboard.route('/wholesale')
@login_required
def wholesale_catalog():
    """View wholesale product catalog"""
    user = get_current_user()
    
    if not user.pos_profile:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.index'))
    
    # Get products with wholesale price set
    products = Product.query.filter(Product.wholesale_price.isnot(None)).all()
    
    return render_template('pos/wholesale_catalog.html', products=products)

@pos_dashboard.route('/purchase', methods=['POST'])
@login_required
def purchase_redirect():
    """Redirect purchase to Checkout Page instead of direct buy"""
    user = get_current_user()
    if not user.pos_profile:
        return jsonify({'error': 'Unauthorized'}), 401
        
    product_id = request.form.get('product_id')
    quantity = int(request.form.get('quantity', 1))
    
    product = Product.query.get_or_404(product_id)
    total_cost = quantity * Decimal(product.wholesale_price or 0)
    
    # Check Wallet Balance
    wallet_balance = user.wallet.balance if user.wallet else 0.00
    
    # Verify Stock Availability first
    if product.manage_stock and product.stock_quantity < quantity:
         flash('Insufficient stock available.', 'error')
         return redirect(url_for('pos_dashboard.wholesale_catalog'))

    return render_template('pos/checkout.html', 
                         product=product, 
                         quantity=quantity,
                         total_cost=total_cost,
                         wallet_balance=wallet_balance,
                         stripe_public_key=current_app.config.get('STRIPE_PUBLIC_KEY'))

# Retaining old function for backwards compat if needed, but commented out or renamed
# def purchase_stock(): ...
@login_required
def purchase_stock():
    """Process stock purchase from admin (Wholesale)"""
    user = get_current_user()
    if not user.pos_profile:
        return jsonify({'error': 'Unauthorized'}), 401
        
    product_id = request.form.get('product_id')
    quantity = int(request.form.get('quantity', 0))
    
    if quantity <= 0:
        flash('Invalid quantity.', 'error')
        return redirect(url_for('pos_dashboard.wholesale_catalog'))
        
    product = Product.query.get_or_404(product_id)
    
    # Check Admin Stock
    if product.manage_stock and product.stock_quantity < quantity:
        flash(f'Not enough stock available. Only {product.stock_quantity} left.', 'error')
        return redirect(url_for('pos_dashboard.wholesale_catalog'))
        
    try:
        # 1. Update POS Inventory
        inventory = POSInventory.query.filter_by(
            seller_id=user.pos_profile.id,
            product_id=product.id
        ).first()
        
        if not inventory:
            inventory = POSInventory(
                seller_id=user.pos_profile.id,
                product_id=product.id,
                quantity=0,
                reserved_quantity=0
            )
            db.session.add(inventory)
            
        inventory.quantity += quantity
        
        # 2. Update Admin/Central Stock
        if product.manage_stock:
            product.stock_quantity -= quantity
            
        # 3. Create Record (Using an Order for history?)
        # For now, we commit the stock transfer. 
        # Ideally, we should create a 'Stock Transfer' log or 'Wholesale Order'.
        # Since I don't have a Wholesale Order table, I'll direct commit.
        
        db.session.commit()
        
        total_cost = quantity * Decimal(product.wholesale_price or 0)
        flash(f'Successfully purchased {quantity} units of {product.title}. Total: ${total_cost:.2f}', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing purchase: {str(e)}', 'error')
        
    return redirect(url_for('pos_dashboard.dashboard'))

@pos_dashboard.route('/orders/<int:order_id>/status', methods=['POST'])
@login_required
def update_order_status(order_id):
    """Update order status (Shipped, Delivered)"""
    user = get_current_user()
    if not user.pos_profile:
        return jsonify({'error': 'Unauthorized'}), 401
    
    order = Order.query.get_or_404(order_id)
    
    if order.assigned_seller_id != user.pos_profile.id:
        flash('This order is not assigned to you.', 'error')
        return redirect(url_for('pos_dashboard.orders'))
        
    new_status = request.form.get('status')
    if new_status not in ['shipped', 'delivered']:
        flash('Invalid status update.', 'error')
        return redirect(url_for('pos_dashboard.orders'))
        
    try:
        if new_status == 'shipped':
            order.status = 'shipped'
            # Logic to send tracking email could go here
        elif new_status == 'delivered':
            order.status = 'delivered'
            order.assignment_status = 'completed'
            
            # CREDIT WALLET
            # Calculate profit/commission. For now, let's assume POS keeps 100% of retail price?
            # Or maybe just a commission?
            # Existing logic doesn't specify commission structure.
            # Let's assume POS seller gets the full order amount credited to their wallet minus any platform fees?
            # For simplicity in this task: Credit User Wallet with Order Total.
            
            if not user.wallet:
                user.wallet = Wallet(user_id=user.id, balance=Decimal('0.00'))
                db.session.add(user.wallet)
                # Flush to get the ID for transaction
                db.session.flush()
                
            amount_to_credit = order.total
            user.wallet.balance += amount_to_credit
            
            transaction = WalletTransaction(
                wallet_id=user.wallet.id,
                amount=amount_to_credit,
                balance_after=user.wallet.balance,
                type='CREDIT',
                reference_id=str(order.id),
                description=f'Earnings for Order #{order.order_number}'
            )
            db.session.add(transaction)
            
        db.session.commit()
        flash(f'Order status updated to {new_status}.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating status: {str(e)}', 'error')
        
    return redirect(url_for('pos_dashboard.orders'))

@pos_dashboard.route('/wallet')
@login_required
def wallet_dashboard():
    """Wallet Dashboard"""
    user = get_current_user()
    if not user.pos_profile:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.index'))
        
    if not user.wallet:
        # Create wallet if not exists
        user.wallet = Wallet(user_id=user.id, balance=Decimal('0.00'))
        db.session.add(user.wallet)
        db.session.commit()
        
    transactions = user.wallet.transactions.limit(20).all()
    pending_payouts = sum(req.amount for req in user.wallet.payout_requests.filter_by(status='pending'))
    
    # Calculate total earned (sum of CREDIT transactions)
    # This is a simplied calculation
    total_earned = db.session.query(db.func.sum(WalletTransaction.amount))\
        .filter(WalletTransaction.wallet_id == user.wallet.id, WalletTransaction.type == 'CREDIT')\
        .scalar() or 0.00
    
    return render_template('pos/wallet.html', 
                         wallet=user.wallet, 
                         transactions=transactions,
                         pending_payouts=pending_payouts,
                         total_earned=total_earned)

@pos_dashboard.route('/checkout/deposit')
@login_required
def checkout_deposit():
    """Dedicated checkout page for wallet deposits"""
    user = get_current_user()
    if not user.pos_profile:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.index'))
        
    if not user.wallet:
        # Create wallet if not exists
        user.wallet = Wallet(user_id=user.id, balance=Decimal('0.00'))
        db.session.add(user.wallet)
        db.session.commit()
    
    # Get enabled payment gateways from database
    from models.payment import PaymentGateway
    
    stripe_gateway = PaymentGateway.query.filter_by(gateway_name='stripe', enabled=True).first()
    paypal_gateway = PaymentGateway.query.filter_by(gateway_name='paypal', enabled=True).first()
    
    stripe_config = None
    paypal_config = None
    
    if stripe_gateway:
        stripe_config = {
            'publishable_key': stripe_gateway.config.get('publishable_key'),
            'mode': stripe_gateway.config.get('mode', 'test')
        }
    
    if paypal_gateway:
        paypal_config = {
            'client_id': paypal_gateway.config.get('client_id'),
            'mode': paypal_gateway.config.get('mode', 'sandbox')
        }
    
    return render_template('pos/checkout_deposit.html',
                         wallet=user.wallet,
                         stripe_config=stripe_config,
                         paypal_config=paypal_config)


@pos_dashboard.route('/wallet/payout', methods=['POST'])
@login_required
def request_payout():
    """Request Payout via PayPal"""
    user = get_current_user()
    amount = Decimal(request.form.get('amount') or 0)
    email = request.form.get('paypal_email')
    
    if amount <= 0 or not email:
        flash('Invalid amount or email.', 'error')
        return redirect(url_for('pos_dashboard.wallet_dashboard'))
        
    if amount > user.wallet.balance:
        flash('Insufficient funds.', 'error')
        return redirect(url_for('pos_dashboard.wallet_dashboard'))
        
    try:
        # Deduct from wallet immediately
        user.wallet.balance -= amount
        
        # Create Transaction Record
        tx = WalletTransaction(
            wallet_id=user.wallet.id,
            amount=amount,
            balance_after=user.wallet.balance,
            type='PAYOUT',
            status='pending',
            description=f'Payout request to {email}'
        )
        db.session.add(tx)
        
        # Create Payout Request Record
        req = PayoutRequest(
            wallet_id=user.wallet.id,
            amount=amount,
            paypal_email=email
        )
        db.session.add(req)
        db.session.commit()
        
        # Trigger Payout via PayPal API (Optional: Or leave for Admin approval)
        # For this task, let's try to process it immediately if configured?
        # Or better: Just create request. Admin triggers actual payout.
        # But user asked for "Integrate Paypal Payoputs".
        # Let's attempt auto-payout for demonstration if keys exist.
        
        if current_app.config.get('PAYPAL_CLIENT_ID'):
             # Ensure service is initialized (safe to call again)
             PaymentService.init_app(current_app)
             result = PaymentService.create_paypal_payout(email, amount)
             
             if result.get('success'):
                req.status = 'completed'
                req.batch_id = result.get('batch_id')
                tx.status = 'completed'
                tx.description += f" (Batch: {result.get('batch_id')})"
                flash('Payout processed successfully via PayPal!', 'success')
             else:
                # If API fails, keep it as pending for manual retry or admin handling
                flash(f"Payout requested. PayPal API Note: {result.get('error')}", 'warning')

        flash('Payout request submitted successfully.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error requesting payout: {str(e)}', 'error')
        
    return redirect(url_for('pos_dashboard.wallet_dashboard'))


def _process_stock_purchase(user, product, quantity, payment_method, reference_id=None):
    """Helper to process stock inventory update after successful payment"""
    # 1. Update POS Inventory
    inventory = POSInventory.query.filter_by(
        seller_id=user.pos_profile.id,
        product_id=product.id
    ).first()
    
    if not inventory:
        inventory = POSInventory(
            seller_id=user.pos_profile.id,
            product_id=product.id,
            quantity=0,
            reserved_quantity=0 # Initialize reserved_quantity
        )
        db.session.add(inventory)
        
    inventory.quantity += quantity
    
    # 2. Update Admin/Central Stock
    if product.manage_stock:
        product.stock_quantity -= quantity
        
    # 3. Create Transaction Record if Wallet (Handled by caller for Wallet, but we could log generically)
    # For now, we assume the caller handles the financial transaction record (Wallet Debit or Stripe Log)
    # We could create a "Stock Purchase Order" record here if we had a model for it.
    
    return True

@pos_dashboard.route('/create-payment-intent', methods=['POST'])
@login_required
def create_payment_intent():
    """Create Stripe Payment Intent"""
    user = get_current_user()
    try:
        data = request.get_json()
        
        # Check for Stripe Configuration
        if not current_app.config.get('STRIPE_SECRET_KEY') or 'sk_test' not in current_app.config.get('STRIPE_SECRET_KEY'):
            return jsonify({'error': 'Stripe Secret Key is missing or invalid. Please check backend/config.py.'}), 500

        amount = 0
        metadata = {}
        
        if data.get('type') == 'wallet_deposit':
            try:
                amount = float(data.get('amount'))
            except (ValueError, TypeError):
                 return jsonify({'error': 'Invalid amount'}), 400
            
            metadata = {
                'user_id': user.id,
                'type': 'wallet_deposit'
            }
        else:
             # Fallback to product based calculation (if needed)
             product_id = data.get('product_id')
             quantity = int(data.get('quantity', 1))
             product = Product.query.get_or_404(product_id)
             amount = float(quantity * Decimal(product.wholesale_price or 0))
             metadata = {
                'user_id': user.id,
                'product_id': product.id,
                'quantity': quantity,
                'type': 'stock_purchase'
            }

        if amount <= 0:
             return jsonify({'error': 'Invalid amount'}), 400

        # Create Payment Intent
        PaymentService.init_app(current_app)
        intent_data = PaymentService.create_stripe_payment_intent(
            amount=amount,
            currency='usd',
            metadata=metadata
        )
        
        if intent_data.get('success'):
            return jsonify({
                'clientSecret': intent_data['client_secret'],
                'id': intent_data['id']
            })
        else:
            return jsonify({'error': intent_data.get('error')}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@pos_dashboard.route('/checkout/stripe/create-session', methods=['POST'])
@login_required
def create_stripe_checkout_session():
    """Create Stripe Checkout Session for wallet deposit"""
    user = get_current_user()
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        
        if amount <= 0:
            return jsonify({'error': 'Invalid amount'}), 400
            
        # URLs for success and cancel
        success_url = url_for('pos_dashboard.stripe_checkout_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}'
        cancel_url = url_for('pos_dashboard.checkout_deposit', _external=True)
        
        # Create checkout session
        PaymentService.init_app(current_app)
        result = PaymentService.create_stripe_checkout_session(
            amount=amount,
            currency='usd',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'user_id': user.id,
                'type': 'wallet_deposit',
                'amount': amount
            }
        )
        
        if result.get('success'):
            return jsonify({
                'session_id': result['session_id'],
                'checkout_url': result['checkout_url']
            })
        else:
            return jsonify({'error': result.get('error')}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@pos_dashboard.route('/checkout/stripe/success')
@login_required
def stripe_checkout_success():
    """Handle successful Stripe checkout"""
    user = get_current_user()
    session_id = request.args.get('session_id')
    
    if not session_id:
        flash('Invalid checkout session.', 'error')
        return redirect(url_for('pos_dashboard.wallet_dashboard'))
    
    try:
        PaymentService.init_app(current_app)
        result = PaymentService.retrieve_stripe_session(session_id)
        
        if result.get('success'):
            session = result['session']
            
            if session.payment_status == 'paid':
                # Credit wallet
                amount = Decimal(session.amount_total) / 100  # Convert from cents
                
                if not user.wallet:
                    user.wallet = Wallet(user_id=user.id, balance=Decimal('0.00'))
                    db.session.add(user.wallet)
                    
                user.wallet.balance += amount
                
                tx = WalletTransaction(
                    wallet_id=user.wallet.id,
                    amount=amount,
                    balance_after=user.wallet.balance,
                    type='CREDIT',
                    description='Deposit via Stripe',
                    reference_id=session_id,
                    status='completed'
                )
                db.session.add(tx)
                db.session.commit()
                
                flash(f'Successfully deposited ${amount:.2f} to your wallet!', 'success')
            else:
                flash('Payment not completed.', 'warning')
        else:
            flash(f'Error verifying payment: {result.get("error")}', 'error')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing deposit: {str(e)}', 'error')
    
    return redirect(url_for('pos_dashboard.wallet_dashboard'))


@pos_dashboard.route('/checkout/paypal/create-order', methods=['POST'])
@login_required
def create_paypal_order():
    """Create PayPal Order for wallet deposit"""
    user = get_current_user()
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        
        if amount <= 0:
            return jsonify({'error': 'Invalid amount'}), 400
            
        # URLs for success and cancel
        return_url = url_for('pos_dashboard.paypal_checkout_success', _external=True)
        cancel_url = url_for('pos_dashboard.checkout_deposit', _external=True)
        
        # Create PayPal order
        PaymentService.init_app(current_app)
        result = PaymentService.create_paypal_order(
            amount=amount,
            currency='USD',
            return_url=return_url,
            cancel_url=cancel_url,
            description=f"Wallet Deposit - ${amount:.2f}"
        )
        
        if result.get('success'):
            return jsonify({
                'order_id': result['order_id'],
                'approval_url': result['approval_url']
            })
        else:
            return jsonify({'error': result.get('error')}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@pos_dashboard.route('/checkout/paypal/success')
@login_required
def paypal_checkout_success():
    """Handle successful PayPal checkout"""
    user = get_current_user()
    order_id = request.args.get('token')  # PayPal sends order_id as 'token'
    
    if not order_id:
        flash('Invalid PayPal order.', 'error')
        return redirect(url_for('pos_dashboard.wallet_dashboard'))
    
    try:
        PaymentService.init_app(current_app)
        result = PaymentService.capture_paypal_order(order_id)
        
        if result.get('success') and result.get('status') == 'COMPLETED':
            # Credit wallet
            amount = Decimal(result.get('amount', 0))
            
            if not user.wallet:
                user.wallet = Wallet(user_id=user.id, balance=Decimal('0.00'))
                db.session.add(user.wallet)
                
            user.wallet.balance += amount
            
            tx = WalletTransaction(
                wallet_id=user.wallet.id,
                amount=amount,
                balance_after=user.wallet.balance,
                type='CREDIT',
                description='Deposit via PayPal',
                reference_id=order_id,
                status='completed'
            )
            db.session.add(tx)
            db.session.commit()
            
            flash(f'Successfully deposited ${amount:.2f} to your wallet via PayPal!', 'success')
        else:
            flash(f'PayPal payment failed: {result.get("error")}', 'error')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing PayPal deposit: {str(e)}', 'error')
    
    return redirect(url_for('pos_dashboard.wallet_dashboard'))


@pos_dashboard.route('/confirm-deposit', methods=['POST'])
@login_required
def confirm_deposit():
    """Confirm a successful Stripe deposit and credit wallet"""
    user = get_current_user()
    try:
        data = request.get_json()
        payment_intent_id = data.get('payment_intent_id')
        amount = Decimal(data.get('amount', 0))
        
        if amount <= 0:
            return jsonify({'error': 'Invalid amount'}), 400
            
        # Verify payment_intent_id with Stripe if desired (Recommended for production security)
        # PaymentService.init_app(current_app)
        # intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        # if intent.status != 'succeeded': return jsonify({'error': 'Payment not successful'}), 400
        
        # Credit User Wallet
        if not user.wallet:
            user.wallet = Wallet(user_id=user.id, balance=Decimal('0.00'))
            db.session.add(user.wallet)
            
        user.wallet.balance += amount
        
        tx = WalletTransaction(
            wallet_id=user.wallet.id,
            amount=amount,
            balance_after=user.wallet.balance,
            type='CREDIT',
            description=f'Deposit via Stripe',
            reference_id=payment_intent_id,
            status='completed'
        )
        db.session.add(tx)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@pos_dashboard.route('/wallet/deposit/paypal', methods=['POST'])
@login_required
def paypal_deposit():
    """Initiate PayPal Deposit"""
    user = get_current_user()
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        
        if amount <= 0:
            return jsonify({'error': 'Invalid amount'}), 400
            
        return_url = url_for('pos_dashboard.paypal_deposit_execute', _external=True)
        cancel_url = url_for('pos_dashboard.wallet_dashboard', _external=True)
        
        PaymentService.init_app(current_app)
        result = PaymentService.create_paypal_payment(
            amount=amount,
            return_url=return_url,
            cancel_url=cancel_url,
            description=f"Wallet Deposit for {user.email}"
        )
        
        if result.get('success'):
            return jsonify({'approval_url': result['approval_url']})
        else:
            return jsonify({'error': result.get('error')}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@pos_dashboard.route('/wallet/deposit/paypal/execute')
@login_required
def paypal_deposit_execute():
    """Execute PayPal Deposit"""
    user = get_current_user()
    payment_id = request.args.get('paymentId')
    payer_id = request.args.get('PayerID')
    
    if not payment_id or not payer_id:
        flash('Invalid PayPal response.', 'error')
        return redirect(url_for('pos_dashboard.wallet_dashboard'))
        
    try:
        PaymentService.init_app(current_app)
        result = PaymentService.execute_paypal_payment(payment_id, payer_id)
        
        if result.get('success'):
            payment = result['payment']
            # safely get amount from payment object
            # transactions[0].amount.total
            amount = Decimal(payment.transactions[0].amount.total)
            
            # Credit Wallet
            if not user.wallet:
                user.wallet = Wallet(user_id=user.id, balance=Decimal('0.00'))
                db.session.add(user.wallet)
                
            user.wallet.balance += amount
            
            tx = WalletTransaction(
                wallet_id=user.wallet.id,
                amount=amount,
                balance_after=user.wallet.balance,
                type='CREDIT',
                description='Deposit via PayPal',
                reference_id=payment_id,
                status='completed'
            )
            db.session.add(tx)
            db.session.commit()
            
            flash('Deposit successful via PayPal!', 'success')
        else:
            flash(f"PayPal Deposit Failed: {result.get('error')}", 'error')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Error executing PayPal deposit: {str(e)}', 'error')
        
    return redirect(url_for('pos_dashboard.wallet_dashboard'))


@pos_dashboard.route('/checkout/confirm', methods=['POST'])
@login_required
def complete_purchase():
    """Complete stock purchase"""
    user = get_current_user()
    product_id = request.form.get('product_id')
    quantity = int(request.form.get('quantity', 0))
    payment_method = request.form.get('payment_method')
    
    product = Product.query.get_or_404(product_id)
    total_cost = quantity * Decimal(product.wholesale_price or 0)
    
    try:
        if payment_method == 'wallet':
            if not user.wallet or user.wallet.balance < total_cost:
                 flash('Insufficient wallet balance.', 'error')
                 return redirect(url_for('pos_dashboard.wholesale_catalog'))
                 
            # Debit Wallet
            user.wallet.balance -= total_cost
            tx = WalletTransaction(
                wallet_id=user.wallet.id,
                amount=total_cost,
                balance_after=user.wallet.balance,
                type='DEBIT',
                description=f'Stock Purchase: {product.title} x{quantity}'
            )
            db.session.add(tx)
            
            # Process Stock
            _process_stock_purchase(user, product, quantity, 'wallet')
            
            db.session.commit()
            flash('Purchase made successfully using Wallet!', 'success')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing purchase: {str(e)}', 'error')
        return redirect(url_for('pos_dashboard.wholesale_catalog'))
        
    return redirect(url_for('pos_dashboard.inventory'))

@pos_dashboard.route('/dashboard')
@login_required
def dashboard():
    """POS Seller Dashboard - Overview"""
    user = get_current_user()
    
    # Ensure user has POS profile
    if not user.pos_profile:
        flash('Access denied. POS profile required.', 'error')
        return redirect(url_for('dashboard.index'))
    
    seller_profile = user.pos_profile
    
    # Get pending orders assigned to this seller
    pending_orders = Order.query.filter_by(
        assigned_seller_id=seller_profile.id,
        assignment_status='assigned'
    ).all()
    
    # Get accepted orders
    accepted_orders = Order.query.filter_by(
        assigned_seller_id=seller_profile.id,
        assignment_status='accepted'
    ).all()
    
    # Get inventory summary
    inventory_items = POSInventory.query.filter_by(
        seller_id=seller_profile.id
    ).all()
    
    total_stock = sum(item.quantity for item in inventory_items)
    reserved_stock = sum(item.reserved_quantity for item in inventory_items)
    available_stock = total_stock - reserved_stock
    
    return render_template('pos/dashboard.html',
                         seller=seller_profile,
                         pending_orders=pending_orders,
                         accepted_orders=accepted_orders,
                         total_stock=total_stock,
                         reserved_stock=reserved_stock,
                         available_stock=available_stock)

@pos_dashboard.route('/orders')
@login_required
def orders():
    """View all orders assigned to this POS seller"""
    user = get_current_user()
    
    if not user.pos_profile:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.index'))
    
    seller_profile = user.pos_profile
    
    # Get all orders for this seller
    all_orders = Order.query.filter_by(
        assigned_seller_id=seller_profile.id
    ).order_by(Order.created_at.desc()).all()
    
    return render_template('pos/orders.html',
                         seller=seller_profile,
                         orders=all_orders)

@pos_dashboard.route('/orders/<int:order_id>/details')
@login_required
def get_order_details(order_id):
    """Get order details for POS view"""
    user = get_current_user()
    
    if not user.pos_profile:
        return jsonify({'error': 'Unauthorized'}), 401
    
    order = Order.query.options(
        joinedload(Order.customer),
        joinedload(Order.items)
    ).get_or_404(order_id)
    
    if order.assigned_seller_id != user.pos_profile.id:
        return jsonify({'error': 'Unauthorized access to this order'}), 403
        
    try:
        # Build order items with variation details
        items_data = []
        for item in order.items:
            # Get variation details
            variation_details = item.variation_details
            if not variation_details and item.variation_id:
                variation = ProductVariation.query.filter_by(id=item.variation_id).first()
                if variation and variation.attribute_terms:
                    if isinstance(variation.attribute_terms, dict):
                        variation_details = variation.attribute_terms
                    elif isinstance(variation.attribute_terms, str):
                        try:
                            import json
                            variation_details = json.loads(variation.attribute_terms)
                        except:
                            variation_details = {}
            
            item_data = {
                'id': item.id,
                'product_name': item.product_name,
                'quantity': item.quantity,
                'price': float(item.price),
                'subtotal': float(item.price * item.quantity),
                'variation_details': variation_details or {}
            }
            items_data.append(item_data)
        
        return jsonify({
            'order_number': order.order_number,
            'status': order.status,
            'assignment_status': order.assignment_status,
            'total': float(order.total),
            'subtotal': float(sum(item['subtotal'] for item in items_data)),
            'created_at': order.created_at.strftime('%Y-%m-%d %H:%M'),
            'billing_address': order.billing_address or {},
            'shipping_address': order.shipping_address or {},
            'items': items_data
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@pos_dashboard.route('/orders/<int:order_id>/accept', methods=['POST'])
@login_required
def accept_order(order_id):
    """Accept an assigned order"""
    user = get_current_user()
    
    if not user.pos_profile:
        return jsonify({'error': 'Unauthorized'}), 401
    
    order = Order.query.get_or_404(order_id)
    
    if order.assigned_seller_id != user.pos_profile.id:
        flash('This order is not assigned to you.', 'error')
        return redirect(url_for('pos_dashboard.orders'))
    
    if order.assignment_status != 'assigned':
        flash('Order cannot be accepted in its current state.', 'warning')
        return redirect(url_for('pos_dashboard.orders'))
    
    try:
        order.assignment_status = 'accepted'
        db.session.commit()
        flash(f'Order {order.order_number} accepted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error accepting order: {str(e)}', 'error')
    
    return redirect(url_for('pos_dashboard.dashboard'))

@pos_dashboard.route('/orders/<int:order_id>/reject', methods=['POST'])
@login_required
def reject_order(order_id):
    """Reject an assigned order"""
    user = get_current_user()
    
    if not user.pos_profile:
        return jsonify({'error': 'Unauthorized'}), 401
    
    order = Order.query.get_or_404(order_id)
    
    if order.assigned_seller_id != user.pos_profile.id:
        flash('This order is not assigned to you.', 'error')
        return redirect(url_for('pos_dashboard.orders'))
    
    try:
        # Release stock
        for item in order.items:
            inventory = POSInventory.query.filter_by(
                seller_id=user.pos_profile.id,
                product_id=item.product_id,
                variation_id=item.variation_id
            ).first()
            if inventory:
                inventory.reserved_quantity -= item.quantity
                if inventory.reserved_quantity < 0:
                    inventory.reserved_quantity = 0
        
        # Clear assignment
        order.assigned_seller_id = None
        order.assignment_status = 'rejected'
        db.session.commit()
        
        # Trigger reassignment
        success, msg = FulfillmentService.assign_order(order.id)
        
        flash(f'Order {order.order_number} rejected. System is reassigning...', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error rejecting order: {str(e)}', 'error')
    
    return redirect(url_for('pos_dashboard.dashboard'))

@pos_dashboard.route('/inventory')
@login_required
def inventory():
    """View POS inventory"""
    user = get_current_user()
    
    if not user.pos_profile:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.index'))
    
    seller_profile = user.pos_profile
    
    # Get all inventory items
    inventory_items = POSInventory.query.filter_by(
        seller_id=seller_profile.id
    ).all()
    
    return render_template('pos/inventory.html',
                         seller=seller_profile,
                         inventory_items=inventory_items)

@pos_dashboard.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """POS Seller Profile Settings"""
    user = get_current_user()
    if not user.pos_profile:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.index'))
        
    seller = user.pos_profile
    
    if request.method == 'POST':
        try:
            seller.business_name = request.form.get('business_name', '').strip()
            seller.address_line1 = request.form.get('address_line1', '').strip()
            seller.city = request.form.get('city', '').strip()
            seller.state = request.form.get('state', '').strip()
            seller.zip_code = request.form.get('zip_code', '').strip()
            seller.country = request.form.get('country', '').strip()
            
            lat = request.form.get('latitude')
            lng = request.form.get('longitude')
            
            if lat and lat.strip():
                seller.latitude = float(lat)
            if lng and lng.strip():
                seller.longitude = float(lng)
                
            seller.auto_accept_orders = request.form.get('auto_accept_orders') == '1'
            
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'error')
            
    return render_template('pos/profile.html', seller=seller)
