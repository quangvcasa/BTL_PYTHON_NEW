import os
import sys

from app import create_app
from app.models import db, User

if len(sys.argv) != 2:
    print('Usage: python delete_admin.py <username>')
    sys.exit(1)

target_username = sys.argv[1]

app = create_app()
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
    print(f'Success: Admin user "{target_username}" has been permanently deleted from database.')
