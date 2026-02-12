import sys
import os

# Add the current directory to likely path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

# Create the application instance
app = create_app()

# Passenger usually looks for 'application', but the traceback says it looks for 'wsgi.app'
# So we provide 'app'. We also provide 'application' just in case.
application = app
