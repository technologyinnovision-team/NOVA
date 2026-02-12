import sys
import os
sys.path.append(os.getcwd())
from app import create_app
from models.setting import Setting

app = create_app()

with app.app_context():
    print("--- Current Database Settings ---")
    settings = ['smtp_host', 'smtp_port', 'smtp_username', 'smtp_password', 'smtp_enabled', 'admin_notification_emails', 'admin_primary_email']
    for key in settings:
        val = Setting.get(key)
        # Mask password
        if 'password' in key and val:
            val = '*' * len(str(val))
        print(f"{key}: '{val}'")
