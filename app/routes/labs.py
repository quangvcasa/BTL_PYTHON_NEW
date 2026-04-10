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


bp = Blueprint('labs', __name__)

@bp.route('/labs')
@login_required
def labs_list():
    if not current_user.is_admin():
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('main.dashboard'))

    labs_list = Lab.query.order_by(Lab.created_at.desc()).all()
    return render_template('labs/list.html', labs=labs_list)


@bp.route('/labs/create', methods=['GET', 'POST'])
@login_required
def labs_create():
    if not current_user.is_admin():
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        manager_name = request.form.get('manager_name')
        email = request.form.get('email')

        lab = Lab(name=name, description=description, manager_name=manager_name, email=email)
        db.session.add(lab)
        db.session.commit()

        flash(f'Lab "{name}" đã được tạo thành công!', 'success')
        return redirect(url_for('labs.labs_list'))

    return render_template('labs/form.html', lab=None, action='Tạo Lab mới')


@bp.route('/labs/edit/<int:lab_id>', methods=['GET', 'POST'])
@login_required
def labs_edit(lab_id):
    if not current_user.is_admin():
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('main.dashboard'))

    lab = Lab.query.get_or_404(lab_id)

    if request.method == 'POST':
        lab.name = request.form.get('name')
        lab.description = request.form.get('description')
        lab.manager_name = request.form.get('manager_name')
        lab.email = request.form.get('email')

        db.session.commit()
        flash(f'Lab "{lab.name}" đã được cập nhật!', 'success')
        return redirect(url_for('labs.labs_list'))

    return render_template('labs/form.html', lab=lab, action='Chỉnh sửa Lab')


@bp.route('/labs/delete/<int:lab_id>', methods=['POST'])
@login_required
def labs_delete(lab_id):
    if not current_user.is_admin():
        flash('Bạn không có quyền thực hiện thao tác này.', 'danger')
        return redirect(url_for('labs.labs_list'))

    lab = Lab.query.get_or_404(lab_id)
    lab_name = lab.name

    # Delete related commitments first
    Commitment.query.filter_by(lab_id=lab_id).delete()

    # Delete related users (set lab_id to null)
    User.query.filter_by(lab_id=lab_id).update({'lab_id': None})

    # Delete the lab
    db.session.delete(lab)
    db.session.commit()

    flash(f'Lab "{lab_name}" đã được xóa thành công!', 'success')
    return redirect(url_for('labs.labs_list'))
