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


bp = Blueprint('reports', __name__)

@bp.route('/reports')
@login_required
def reports():
    if not current_user.is_admin():
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('main.dashboard'))

    labs = Lab.query.all()

    # Overall stats
    total = Commitment.query.count()
    completed = Commitment.query.filter_by(status='Hoàn thành').count()
    completion_rate = (completed / total * 100) if total > 0 else 0

    # Stats by lab
    lab_data = []
    for lab in labs:
        commits = Commitment.query.filter_by(lab_id=lab.id).all()
        total_lab = len(commits)
        completed_lab = len([c for c in commits if c.status == 'Hoàn thành'])
        overdue_lab = len([c for c in commits if c.status == 'Quá hạn'])
        lab_data.append({
            'name': lab.name,
            'total': total_lab,
            'completed': completed_lab,
            'overdue': overdue_lab,
            'rate': (completed_lab / total_lab * 100) if total_lab > 0 else 0
        })

    # Chart data
    status_dist = db.session.query(
        Commitment.status,
        db.func.count(Commitment.id)
    ).group_by(Commitment.status).all()

    chart_labels = [s[0] for s in status_dist]
    chart_data = [s[1] for s in status_dist]

    return render_template('reports/index.html',
                           labs=labs,
                           total=total,
                           completed=completed,
                           completion_rate=completion_rate,
                           lab_data=lab_data,
                           chart_labels=chart_labels,
                           chart_data=chart_data)
