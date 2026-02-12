from flask import Flask, send_from_directory, render_template_string
from flask_session import Session
from config import Config
from models import db
from models.user import User, Role
from utils.auth import hash_password, get_current_user
from utils.integrations import get_integration_codes, get_individual_integration_codes
import os

# Import blueprints
from routes.auth import auth
from routes.dashboard import dashboard

def create_app():
    """Application factory"""
    # Get the base directory (Backend folder)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    build_dir = os.path.join(base_dir, 'build')
    
    # Don't use static_url_path='' to avoid Flask trying to serve everything as static files
    # Instead, we'll handle static files manually in the catch-all route
    app = Flask(__name__, 
                static_folder=None)  # Disable automatic static file serving
    app.config.from_object(Config)
    
    # Enable CORS for all domains on all routes
    from flask_cors import CORS
    CORS(app, resources={r"/*": {"origins": "*"}})
    
    # Initialize extensions
    db.init_app(app)
    from flask_migrate import Migrate, upgrade
    migrate = Migrate(app, db)

    # Run DB Migrations on Startup
    with app.app_context():
        # Avoid running migrations when just building or testing
        # Check if table exists to avoid errors on fresh install before create_all
        # Actually create_all is called below, upgrade handles migrations. 
        # But if we use create_all, migrate stamps might be missing for initial tables.
        # Best practice: use migrations for everything. But here we have potential mixed usage.
        # We will try to upgrade only if not in a special mode.
        try:
             upgrade()
             print("Database migrations applied successfully.")
        except Exception as e:
             print(f"Migration warning: {e}")
    
    # Configure session
    app.config['SESSION_TYPE'] = 'sqlalchemy'
    app.config['SESSION_SQLALCHEMY'] = db
    app.config['SESSION_SQLALCHEMY_TABLE'] = 'sessions'
    app.config['SESSION_PERMANENT'] = False
    app.config['SESSION_USE_SIGNER'] = True
    app.config['SESSION_KEY_PREFIX'] = 'bailebelle:session:'
    
    # Initialize Session
    # Handle the case where the Flask-Session model is already defined
    try:
        from sqlalchemy.exc import InvalidRequestError
        Session(app)
        
        # [PATCH] Use Custom Session Interface to handle IntegrityError/Race conditions
        # Capture the existing session model to avoid re-declaration
        existing_model = app.session_interface.sql_session_model if hasattr(app.session_interface, 'sql_session_model') else None
        
        from utils.custom_session import CustomSqlAlchemySessionInterface
        app.session_interface = CustomSqlAlchemySessionInterface(
            app, db, 'sessions', 'bailebelle:session:', 
            use_signer=True, permanent=False,
            sql_session_model=existing_model
        )
    except InvalidRequestError:
        # If the session model is already defined, we can ignore this error
        # This typically happens during reloading or if models are imported multiple times
        pass
    
    # Register blueprints
    app.register_blueprint(auth)
    app.register_blueprint(dashboard)
    
    # Register POS Dashboard
    from routes.pos_dashboard import pos_dashboard
    app.register_blueprint(pos_dashboard)
    
    # Import and register other blueprints
    from routes.products import products
    from routes.categories import categories
    from routes.orders import orders
    from routes.customers import customers
    from routes.shipping_admin import shipping_admin
    from routes.payments import payments
    from routes.integrations import integrations
    from routes.settings import settings
    from routes.api_keys import api_keys
    from routes.blogs import blogs
    from routes.coupons import coupons
    
    app.register_blueprint(products)
    app.register_blueprint(categories)
    app.register_blueprint(orders)
    app.register_blueprint(customers)
    app.register_blueprint(shipping_admin)
    app.register_blueprint(payments)
    app.register_blueprint(integrations)
    app.register_blueprint(settings)
    app.register_blueprint(api_keys)

    app.register_blueprint(blogs)
    
    from routes.users import users_bp
    app.register_blueprint(users_bp)
    
    # API Blueprints
    from api.shipping import shipping_bp as api_shipping_bp
    from api.tax import tax_bp as api_tax_bp
    
    app.register_blueprint(api_shipping_bp, url_prefix='/api/v1/shipping')
    app.register_blueprint(api_tax_bp, url_prefix='/api/v1/tax')
    app.register_blueprint(coupons)
    
    from routes.deals_admin import deals_admin_bp
    app.register_blueprint(deals_admin_bp)

    from routes.home_sections import home_sections_bp
    app.register_blueprint(home_sections_bp)
    

    
    from routes.media import media
    app.register_blueprint(media)

    from routes.backups import backups
    app.register_blueprint(backups)

    from routes.file_manager import file_manager
    app.register_blueprint(file_manager)

    
    from routes.seo import seo_bp
    app.register_blueprint(seo_bp)

    from routes.updates import updates_bp
    app.register_blueprint(updates_bp)

    
    # Register API blueprints
    from api import api_v1
    app.register_blueprint(api_v1)
    
    from api.pos_api import pos_bp
    app.register_blueprint(pos_bp)
    
    from api.admin_fulfillment_api import admin_fulfillment_bp
    app.register_blueprint(admin_fulfillment_bp)


    
    # Create tables and initial data
    with app.app_context():
        # db.create_all() # Removed to prevent "Table already exists" error. Migrations handle schema.
        create_initial_data()
    
    # Context processor for templates
    @app.context_processor
    def inject_user():
        from utils.auth import get_current_user
        return dict(current_user=get_current_user())
    
    # Serve uploaded files
    @app.route('/uploads/<path:filename>')
    def serve_upload(filename):
        """Serve uploaded files from local storage"""
        uploads_dir = os.path.join(base_dir, 'uploads')
        return send_from_directory(uploads_dir, filename)

    # Serve Backend Static files (CSS/JS for Admin)
    @app.route('/static/<path:filename>', endpoint='static')
    def serve_static(filename):
        """Serve backend static files"""
        static_dir = os.path.join(base_dir, 'static')
        return send_from_directory(static_dir, filename)
    
    # Serve React App - catch-all route must be last
    # This route will only be matched if no blueprint route matches first
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve_react_app(path=''):
        """Serve the React app for all non-API routes with injected integration codes"""
        # Explicitly exclude API routes and uploads (shouldn't reach here, but safety check)
        # Check both with and without leading slash
        normalized_path = path.lstrip('/')
        if (normalized_path.startswith('api/v1/') or 
            normalized_path.startswith('api/') or 
            normalized_path.startswith('uploads/') or
            path.startswith('/api/v1/') or 
            path.startswith('/api/') or 
            path.startswith('/uploads/')):
            from flask import abort
            abort(404)
        
        # Normalize path (remove trailing slash for consistency)
        normalized_path = path.rstrip('/') if path else ''
        
        # Check if it's a static file request (JS, CSS, images, etc.)
        # Static files have extensions like .js, .css, .jpg, etc.
        if normalized_path:
            # Common static file extensions
            static_extensions = ('.js', '.css', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', 
                               '.ico', '.woff', '.woff2', '.ttf', '.eot', '.json', '.map', '.xml')
            
            # Check if it's a static file by extension
            if normalized_path.lower().endswith(static_extensions):
                static_file_path = os.path.join(build_dir, normalized_path)
                if os.path.isfile(static_file_path):
                    return send_from_directory(build_dir, normalized_path)
                # If static file doesn't exist, return 404
                from flask import abort
                abort(404)
            
            # Check if it's a directory with index.html inside
            static_file_path = os.path.join(build_dir, normalized_path)
            if os.path.isdir(static_file_path):
                dir_index = os.path.join(static_file_path, 'index.html')
                if os.path.isfile(dir_index):
                    return send_from_directory(build_dir, os.path.join(normalized_path, 'index.html'))
        
        # For all SPA routes (including /checkout, /collections, etc.), serve index.html
        # This allows React Router to handle client-side routing
        index_path = os.path.join(build_dir, 'index.html')
        if os.path.isfile(index_path):
            try:
                with open(index_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # Get integration codes
                with app.app_context():
                    codes = get_integration_codes()
                    individual_codes = get_individual_integration_codes()
                
                # Render the HTML as a Jinja template with integration codes
                rendered_html = render_template_string(
                    html_content,
                    # Combined codes for header/body/footer sections
                    header_code=codes.get('header', ''),
                    body_code=codes.get('body', ''),
                    footer_code=codes.get('footer', ''),
                    # Individual codes for template variables
                    user=get_current_user(),
                )
                
                from flask import Response
                return Response(rendered_html, mimetype='text/html')
            except Exception as e:
                # If injection fails, serve original file
                print(f"Error injecting integration codes: {e}")
                return send_from_directory(build_dir, 'index.html')
        
        # Fallback: serve index.html (React Router will handle routing)
        return send_from_directory(build_dir, 'index.html')
    
    return app

def create_initial_data():
    """Create initial roles and admin user"""
    # Create roles
    try:
        from sqlalchemy.exc import ProgrammingError, OperationalError
        if Role.query.count() == 0:
            super_admin = Role(
                name='Super Admin',
                permissions={
                    'all': True,
                    'products': True,
                    'categories': True,
                    'orders': True,
                    'customers': True,
                    'shipping': True,
                    'payments': True,
                    'integrations': True,
                    'settings': True,
                    'users': True,
                }
            )
            
            manager = Role(
                name='Manager',
                permissions={
                    'all': False,
                    'products': True,
                    'categories': True,
                    'orders': True,
                    'customers': True,
                    'shipping': True,
                    'payments': False,
                    'integrations': True,
                    'settings': False,
                    'users': False,
                }
            )
            
            editor = Role(
                name='Editor',
                permissions={
                    'all': False,
                    'products': True,
                    'categories': True,
                    'orders': False,
                    'customers': False,
                    'shipping': False,
                    'payments': False,
                    'integrations': False,
                    'settings': False,
                    'users': False,
                }
            )

            pos_seller = Role(
                name='POS Seller',
                permissions={
                    'all': False,
                    'products': False,
                    'categories': False,
                    'orders': True, # To view/accept assigned orders
                    'customers': False,
                    'shipping': True, # To manage shipping
                    'payments': False,
                    'integrations': False,
                    'settings': False,
                    'users': False,
                    'pos_access': True # Custom permission flag
                }
            )
            
            db.session.add(super_admin)
            db.session.add(manager)
            db.session.add(editor)
            db.session.add(pos_seller)
            db.session.commit()
    except (ProgrammingError, OperationalError):
        print("Database tables not created yet. Skipping initial data creation.")
        return
    
    # Create default admin user
    if User.query.filter_by(username='admin').first() is None:
        admin_role = Role.query.filter_by(name='Super Admin').first()
        if admin_role:
            admin = User(
                username='admin',
                email='fahadstylesofficial@gmail.com',
                password_hash=hash_password('ShahFahadCEO7376@'),  # Change this in production!
                role_id=admin_role.id
            )
            db.session.add(admin)
            db.session.commit()
            print("Default admin user created: username='admin', password='ShahFahadCEO7376@'")




# Create the application instance for production/WSGI
app = create_app()

if __name__ == '__main__':
    # Development server only - use Supervisor for production
    import os
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'True').lower() in ('true', '1', 'yes')
    app.run(debug=debug, host=host, port=port)


