from app import create_app, db
from flask_migrate import stamp
import sys

# Initialize app
app = create_app()

with app.app_context():
    try:
        print("Creating all database tables...")
        db.create_all()
        print("successfully created all database tables")
        
        print("Stamping migration head...")
        stamp()
        print("Migration head stamped successfully")
        
        print("Database fixed successfully!")
    except Exception as e:
        print(f"Error fixing database: {e}")
        sys.exit(1)
