r"""
delete_admin.py — Safely delete a specific user by username.

Usage:
    # Set SECRET_KEY first (required by app config)
    # Windows PowerShell:
    $env:SECRET_KEY = "any-value-for-local-testing"
    .venv\Scripts\python.exe delete_admin.py admin

    # Windows CMD:
    set SECRET_KEY=any-value-for-local-testing
    .venv\Scripts\python.exe delete_admin.py admin

    # Linux / Mac:
    SECRET_KEY=any-value python delete_admin.py admin
"""
import os
import sys

# SECRET_KEY must exist or config.py will raise.
if not os.environ.get('SECRET_KEY'):
    print('[ERROR] Set SECRET_KEY environment variable before running this script.')
    sys.exit(1)

if len(sys.argv) != 2:
    print('Usage: python delete_admin.py <username>')
    sys.exit(1)

target_username = sys.argv[1]

from app import app
from models import db, User

with app.app_context():
    user = User.query.filter_by(username=target_username).first()
    if user is None:
        print(f'User "{target_username}" not found — nothing deleted.')
        sys.exit(0)

    if user.role != 'admin':
        # Safety guard: refuse to delete non-admin users with this script.
        print(f'[ABORTED] User "{target_username}" is not an admin (role={user.role}).')
        print('This script is intended for admin users only.')
        sys.exit(1)

    db.session.delete(user)
    db.session.commit()
    print(f'Admin user "{target_username}" deleted successfully.')
