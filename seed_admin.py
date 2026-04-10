"""
seed_admin.py — Create the first admin user from environment variables.

Usage (Windows):
    set SECRET_KEY=<your-secret>
    set ADMIN_USERNAME=<choose-a-username>
    set ADMIN_PASSWORD=<choose-a-strong-password>
    .venv\Scripts\python.exe seed_admin.py

Usage (Linux/Mac):
    SECRET_KEY=... ADMIN_USERNAME=... ADMIN_PASSWORD=... python seed_admin.py
"""
import os
import sys

# Validate required env vars before importing app (which itself validates SECRET_KEY).
admin_username = os.environ.get('ADMIN_USERNAME')
admin_password = os.environ.get('ADMIN_PASSWORD')

if not admin_username or not admin_password:
    print('[ERROR] ADMIN_USERNAME and ADMIN_PASSWORD must both be set in environment.')
    sys.exit(1)

from app import app
from models import db, User

with app.app_context():
    if User.query.filter_by(username=admin_username).first():
        print(f'Admin already exists: "{admin_username}" — nothing changed.')
    else:
        admin = User(username=admin_username, role='admin')
        admin.set_password(admin_password)
        db.session.add(admin)
        db.session.commit()
        print(f'Admin created: "{admin_username}"')
