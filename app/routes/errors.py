from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, send_file, current_app, abort
from flask_wtf.csrf import CSRFError
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from datetime import datetime, timedelta
import os
import uuid

from ..extensions import db, csrf
from ..models import User, Lab, Commitment, ProgressUpdate
from ..utils import can_access_lab, can_access_commitment, parse_int_field, parse_date_field, validate_role, validate_lab_id, validate_assigned_to, validate_uploaded_file


bp = Blueprint('errors', __name__)

@bp.app_errorhandler(CSRFError)
def csrf_error(error):
    """Return a friendly error when a CSRF token is missing or invalid."""
    flash('Yêu cầu không hợp lệ: CSRF token thiếu hoặc đã hết hạn. Vui lòng thử lại.', 'danger')
    return redirect(request.referrer or url_for('main.dashboard'))


@bp.app_errorhandler(404)
def not_found(error):
    return render_template('errors/404.html'), 404


@bp.app_errorhandler(RequestEntityTooLarge)
def file_too_large(error):
    """Handle uploads that exceed MAX_CONTENT_LENGTH before they reach route logic."""
    flash('File quá lớn. Giới hạn tối đa là 16 MB.', 'danger')
    return redirect(request.referrer or url_for('main.dashboard')), 413


@bp.app_errorhandler(500)
def server_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

