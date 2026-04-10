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


bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))


@bp.route('/dashboard')
@login_required
def dashboard():
    today = datetime.utcnow().date()

    if current_user.is_admin():
        # Admin sees all
        total = Commitment.query.count()
        active = Commitment.query.filter(Commitment.status == 'Đang thực hiện').count()
        completed = Commitment.query.filter(Commitment.status == 'Hoàn thành').count()
        overdue = Commitment.query.filter(Commitment.status == 'Quá hạn').count()
        new_commits = Commitment.query.filter(Commitment.status == 'Mới').count()

        recent = Commitment.query.order_by(Commitment.updated_at.desc()).limit(10).all()

        # Stats by lab
        lab_stats = db.session.query(
            Lab.name,
            db.func.count(Commitment.id).label('total'),
            db.func.sum(db.case((Commitment.progress >= 100, 1), else_=0)).label('completed')
        ).outerjoin(Commitment).group_by(Lab.id).all()

        # Chart data
        status_chart = {
            'labels': ['Mới', 'Đang thực hiện', 'Hoàn thành', 'Quá hạn'],
            'data': [new_commits, active, completed, overdue]
        }

        labs = Lab.query.all()
        commitments_by_lab = []
        for lab in labs:
            count = Commitment.query.filter_by(lab_id=lab.id).count()
            commitments_by_lab.append({'name': lab.name, 'count': count})

    else:
        # Lab user sees only their lab
        lab_id = current_user.lab_id
        total = Commitment.query.filter_by(lab_id=lab_id).count()
        active = Commitment.query.filter_by(lab_id=lab_id, status='Đang thực hiện').count()
        completed = Commitment.query.filter_by(lab_id=lab_id, status='Hoàn thành').count()
        overdue = Commitment.query.filter_by(lab_id=lab_id, status='Quá hạn').count()
        new_commits = Commitment.query.filter_by(lab_id=lab_id, status='Mới').count()

        recent = Commitment.query.filter_by(lab_id=lab_id).order_by(Commitment.updated_at.desc()).limit(10).all()

        status_chart = {
            'labels': ['Mới', 'Đang thực hiện', 'Hoàn thành', 'Quá hạn'],
            'data': [new_commits, active, completed, overdue]
        }

        labs = None
        commitments_by_lab = None
        lab_stats = None

    return render_template('dashboard.html',
                           total=total, active=active, completed=completed,
                           overdue=overdue, recent=recent,
                           status_chart=status_chart,
                           labs=labs, lab_stats=lab_stats,
                           commitments_by_lab=commitments_by_lab)


@bp.route('/my-tasks')
@login_required
def my_tasks():
    """Page showing tasks assigned to current user"""
    if current_user.is_admin():
        flash('Trang này dành cho user Lab.', 'info')
        return redirect(url_for('main.dashboard'))

    today = datetime.utcnow().date()

    # Get tasks assigned to this user
    my_tasks_list = Commitment.query.filter_by(assigned_to=current_user.id).order_by(Commitment.deadline.asc()).all()

    # Stats
    total = len(my_tasks_list)
    completed = len([t for t in my_tasks_list if t.status == 'Hoàn thành'])
    active = len([t for t in my_tasks_list if t.status == 'Đang thực hiện'])
    overdue = len([t for t in my_tasks_list if t.status == 'Quá hạn'])

    return render_template('my_tasks.html',
                           my_tasks=my_tasks_list,
                           total=total, completed=completed,
                           active=active, overdue=overdue,
                           today=today)


@bp.route('/uploads/<filename>')
@login_required
def download_file(filename):
    """Serve uploaded attachment files with ownership check."""
    # Look up the file in DB — orphan files are not served
    update = ProgressUpdate.query.filter_by(attachment=filename).first()
    if update is None:
        abort(404)

    commitment = update.commitment
    if not can_access_commitment(commitment):
        abort(403)

    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        filename,
        as_attachment=True
    )
