from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, send_file, current_app, abort
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from datetime import datetime, timedelta
import os
import uuid

from ..extensions import db, csrf
from ..models import User, Lab, Commitment, ProgressUpdate
from ..utils import can_access_lab, can_access_commitment, parse_int_field, parse_date_field, validate_role, validate_lab_id, validate_assigned_to, validate_uploaded_file


bp = Blueprint('api', __name__)

@bp.route('/api/stats')
@login_required
def api_stats():
    if current_user.is_admin():
        commitments = Commitment.query.all()
    else:
        commitments = Commitment.query.filter_by(lab_id=current_user.lab_id).all()

    stats = {
        'total': len(commitments),
        'by_status': {},
        'avg_progress': 0
    }

    for c in commitments:
        stats['by_status'][c.status] = stats['by_status'].get(c.status, 0) + 1

    if commitments:
        stats['avg_progress'] = sum(c.progress for c in commitments) / len(commitments)

    return jsonify(stats)


@bp.route('/api/commitments/<int:commitment_id>/timeline')
@login_required
def api_timeline(commitment_id):
    commitment = Commitment.query.get_or_404(commitment_id)

    if not can_access_commitment(commitment):
        return jsonify({'success': False, 'message': 'Không có quyền truy cập'}), 403

    updates = ProgressUpdate.query.filter_by(commitment_id=commitment_id).order_by(ProgressUpdate.created_at).all()

    timeline = [{
        'date': commitment.start_date.isoformat(),
        'progress': 0,
        'note': 'Bắt đầu'
    }]
    timeline.extend([{
        'date': u.created_at.isoformat(),
        'progress': u.progress,
        'note': u.notes
    } for u in updates])

    return jsonify(timeline)


@bp.route('/api/labs/<int:lab_id>/users')
@login_required
def api_lab_users(lab_id):
    """Get all lab users for a specific lab (admin only)"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Không có quyền truy cập'}), 403

    users = User.query.filter_by(lab_id=lab_id, role='lab').all()
    return jsonify([{'id': u.id, 'username': u.username} for u in users])
