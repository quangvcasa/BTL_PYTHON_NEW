import re
import os

with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

# We need to split things up.
# First, let's extract all routes manually or automatically.
# We will just write a new version of the blueprints by copying the exact code and replacing `@app.route` with `@bp.route`.
# Let's generate the files!

def get_imports():
    return """from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, send_file, current_app, abort
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from datetime import datetime, timedelta
import os
import uuid

from ..extensions import db, csrf
from ..models import User, Lab, Commitment, ProgressUpdate
from ..utils import can_access_lab, can_access_commitment, parse_int_field, parse_date_field, validate_role, validate_lab_id, validate_assigned_to, validate_uploaded_file
"""

def extract_routes(patterns):
    code_blocks = []
    for pat in patterns:
        matches = re.finditer(f'(?m)^@app\.route\\({pat}.*?(?=\n@app\.route|\n# ===|\Z)', text, re.DOTALL)
        for m in matches:
            code = m.group(0).strip()
            # replace @app.route with @bp.route
            code = re.sub(r'^@app\.route', '@bp.route', code, flags=re.MULTILINE)
            code_blocks.append(code)
    return "\n\n".join(code_blocks)

# Map blueprints to route prefixes
blueprints = {
    'auth': r"'/login'|'/logout'",
    'main': r"'/'|'/dashboard'|'/my-tasks'|'/uploads/<filename>'",
    'labs': r"'/labs.*?|<int:lab_id>'",  # regex needs careful tuning
    'users': r"'/users.*?|<int:user_id>'",
    'commitments': r"'/commitments.*?|<int:commitment_id>'|'/progress/update/<int:commitment_id>'",
    'reports': r"'/reports'",
    'api': r"'/api/stats'|'/api/commitments/.*?timeline'|'/api/labs/.*?users'"
}

import ast
def generate_bp(name, routes_text):
    content = get_imports()
    content += f"\n\nbp = Blueprint('{name}', __name__)\n\n"
    content += routes_text
    # We should write this to app/routes/{name}.py
    with open(f"app/routes/{name}.py", "w", encoding="utf-8") as f:
        f.write(content)

# We will actually just extract all the blocks by finding every @app.route block
blocks = {}
matches = list(re.finditer(r'(?m)^@app\.route\([\s\S]*?(?=\n@app\.route|\n# ==============|\Z)', text))
for m in matches:
    block = m.group(0)
    route_match = re.search(r"@app\.route\(['\"]([^'\"]+)['\"]", block)
    if not route_match:
        continue
    route = route_match.group(1)
    
    # Assign block to blueprint
    if route in ['/login', '/logout']:
        bp = 'auth'
    elif route in ['/', '/dashboard', '/my-tasks'] or route.startswith('/uploads'):
        bp = 'main'
    elif route.startswith('/users'):
        bp = 'users'
    elif route.startswith('/labs'):
        bp = 'labs'
    elif route.startswith('/commitments') or route.startswith('/progress'):
        bp = 'commitments'
    elif route.startswith('/api'):
        bp = 'api'
    elif route.startswith('/reports'):
        bp = 'reports'
    else:
        bp = 'main'
    
    if bp not in blocks:
        blocks[bp] = []
    
    block = block.replace('@app.route', '@bp.route')
    blocks[bp].append(block)

for bp_name, bp_blocks in blocks.items():
    generate_bp(bp_name, "\n\n".join(bp_blocks))

print("Blueprints generated.")

# Extract error handlers
error_matches = list(re.finditer(r'(?m)^@app\.errorhandler\([\s\S]*?(?=\n@app\.errorhandler|\Z)', text))
err_blocks = [m.group(0).replace('@app.errorhandler', '@bp.app_errorhandler') for m in error_matches]
if err_blocks:
    with open("app/routes/errors.py", "w", encoding="utf-8") as f:
        f.write(get_imports())
        f.write("\n\nbp = Blueprint('errors', __name__)\n\n")
        f.write("\n\n".join(err_blocks))
        print("Error handlers extracted.")
