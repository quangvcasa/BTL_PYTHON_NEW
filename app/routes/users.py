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


bp = Blueprint('users', __name__)

@bp.route('/users')
@login_required
def users_list():
    if not current_user.is_admin():
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('main.dashboard'))

    users = User.query.order_by(User.username).all()
    return render_template('users/list.html', users=users)


@bp.route('/users/create', methods=['GET', 'POST'])
@login_required
def users_create():
    if not current_user.is_admin():
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('main.dashboard'))

    labs = Lab.query.all()

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')

        # --- validate role ---
        role_err = validate_role(role)
        if role_err:
            flash(role_err, 'danger')
            return render_template('users/form.html', user=None, labs=labs, action='Tạo User mới')

        # --- validate lab_id ---
        lab_id_raw = request.form.get('lab_id') if role == 'lab' else None
        lab_id, lab_err = validate_lab_id(lab_id_raw, required=(role == 'lab'))
        if lab_err:
            flash(lab_err, 'danger')
            return render_template('users/form.html', user=None, labs=labs, action='Tạo User mới')

        if User.query.filter_by(username=username).first():
            flash('Tên đăng nhập đã tồn tại!', 'danger')
            return render_template('users/form.html', user=None, labs=labs, action='Tạo User mới')

        user = User(username=username, role=role, lab_id=lab_id)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash(f'User "{username}" đã được tạo thành công!', 'success')
        return redirect(url_for('users.users_list'))

    return render_template('users/form.html', user=None, labs=labs, action='Tạo User mới')


@bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
def users_edit(user_id):
    if not current_user.is_admin():
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('main.dashboard'))

    user = User.query.get_or_404(user_id)
    labs = Lab.query.all()

    if request.method == 'POST':
        new_role = request.form.get('role')

        # --- validate role ---
        role_err = validate_role(new_role)
        if role_err:
            flash(role_err, 'danger')
            return render_template('users/form.html', user=user, labs=labs, action='Chỉnh sửa User')

        # --- validate lab_id ---
        lab_id_raw = request.form.get('lab_id') if new_role == 'lab' else None
        lab_id, lab_err = validate_lab_id(lab_id_raw, required=(new_role == 'lab'))
        if lab_err:
            flash(lab_err, 'danger')
            return render_template('users/form.html', user=user, labs=labs, action='Chỉnh sửa User')

        user.role = new_role
        user.lab_id = lab_id

        new_password = request.form.get('password')
        if new_password:
            user.set_password(new_password)

        db.session.commit()
        flash(f'User "{user.username}" đã được cập nhật!', 'success')
        return redirect(url_for('users.users_list'))

    return render_template('users/form.html', user=user, labs=labs, action='Chỉnh sửa User')


@bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
def users_delete(user_id):
    if not current_user.is_admin():
        flash('Bạn không có quyền thực hiện thao tác này.', 'danger')
        return redirect(url_for('users.users_list'))

    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Không thể xóa chính mình.', 'danger')
        return redirect(url_for('users.users_list'))

    user_name = user.username
    db.session.delete(user)
    db.session.commit()

    flash(f'User "{user_name}" đã được xóa thành công!', 'success')
    return redirect(url_for('users.users_list'))
