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


bp = Blueprint('commitments', __name__)

@bp.route('/commitments')
@login_required
def commitments_list():
    query = Commitment.query

    # Filter by lab for lab users
    if not current_user.is_admin():
        query = query.filter_by(lab_id=current_user.lab_id)

    # Apply filters
    lab_filter = request.args.get('lab_id')
    status_filter = request.args.get('status')
    search = request.args.get('search')

    if lab_filter:
        query = query.filter_by(lab_id=int(lab_filter))
    if status_filter:
        query = query.filter_by(status=status_filter)
    if search:
        query = query.filter(Commitment.title.contains(search))

    commitments = query.order_by(Commitment.deadline.asc()).all()
    labs = Lab.query.all()

    return render_template('commitments/list.html', commitments=commitments, labs=labs)


@bp.route('/commitments/create', methods=['GET', 'POST'])
@login_required
def commitments_create():
    if not current_user.is_admin():
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('main.dashboard'))

    labs = Lab.query.all()
    selected_lab_id = request.args.get('lab_id', type=int)
    lab_users = User.query.filter_by(lab_id=selected_lab_id, role='lab').all() if selected_lab_id else []

    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')

        # --- validate lab_id ---
        lab_id, lab_err = validate_lab_id(request.form.get('lab_id'), required=True)
        if lab_err:
            flash(lab_err, 'danger')
            return render_template('commitments/form.html', commitment=None, labs=labs,
                                   lab_users=lab_users, action='Tạo Cam kết mới')

        # --- validate dates ---
        start_date, sd_err = parse_date_field(request.form.get('start_date'), 'Ngày bắt đầu')
        if sd_err:
            flash(sd_err, 'danger')
            return render_template('commitments/form.html', commitment=None, labs=labs,
                                   lab_users=lab_users, action='Tạo Cam kết mới')
        deadline, dl_err = parse_date_field(request.form.get('deadline'), 'Ngày kết thúc')
        if dl_err:
            flash(dl_err, 'danger')
            return render_template('commitments/form.html', commitment=None, labs=labs,
                                   lab_users=lab_users, action='Tạo Cam kết mới')
        if deadline < start_date:
            flash('Ngày kết thúc không được nhỏ hơn ngày bắt đầu.', 'danger')
            return render_template('commitments/form.html', commitment=None, labs=labs,
                                   lab_users=lab_users, action='Tạo Cam kết mới')

        # --- validate assigned_to ---
        assigned_to, at_err = validate_assigned_user(request.form.get('assigned_to'), lab_id)
        if at_err:
            flash(at_err, 'danger')
            return render_template('commitments/form.html', commitment=None, labs=labs,
                                   lab_users=lab_users, action='Tạo Cam kết mới')

        commitment = Commitment(
            title=title,
            description=description,
            lab_id=lab_id,
            assigned_to=assigned_to,
            start_date=start_date,
            deadline=deadline,
            created_by=current_user.id
        )
        db.session.add(commitment)
        db.session.commit()

        flash(f'Cam kết "{title}" đã được tạo thành công!', 'success')
        return redirect(url_for('commitments.commitments_list'))

    return render_template('commitments/form.html', commitment=None, labs=labs,
                           lab_users=lab_users, action='Tạo Cam kết mới')


@bp.route('/commitments/edit/<int:commitment_id>', methods=['GET', 'POST'])
@login_required
def commitments_edit(commitment_id):
    commitment = Commitment.query.get_or_404(commitment_id)

    # Only admin can edit all, lab can only edit their own
    if not current_user.is_admin() and commitment.lab_id != current_user.lab_id:
        flash('Bạn không có quyền chỉnh sửa cam kết này.', 'danger')
        return redirect(url_for('main.dashboard'))

    labs = Lab.query.all()
    lab_users = User.query.filter_by(lab_id=commitment.lab_id, role='lab').all()

    if request.method == 'POST':
        if current_user.is_admin():
            # --- validate lab_id ---
            lab_id, lab_err = validate_lab_id(request.form.get('lab_id'), required=True)
            if lab_err:
                flash(lab_err, 'danger')
                return render_template('commitments/form.html', commitment=commitment, labs=labs,
                                       lab_users=lab_users, action='Chỉnh sửa Cam kết')

            # --- validate dates ---
            start_date, sd_err = parse_date_field(request.form.get('start_date'), 'Ngày bắt đầu')
            if sd_err:
                flash(sd_err, 'danger')
                return render_template('commitments/form.html', commitment=commitment, labs=labs,
                                       lab_users=lab_users, action='Chỉnh sửa Cam kết')
            deadline, dl_err = parse_date_field(request.form.get('deadline'), 'Ngày kết thúc')
            if dl_err:
                flash(dl_err, 'danger')
                return render_template('commitments/form.html', commitment=commitment, labs=labs,
                                       lab_users=lab_users, action='Chỉnh sửa Cam kết')
            if deadline < start_date:
                flash('Ngày kết thúc không được nhỏ hơn ngày bắt đầu.', 'danger')
                return render_template('commitments/form.html', commitment=commitment, labs=labs,
                                       lab_users=lab_users, action='Chỉnh sửa Cam kết')

            # --- validate assigned_to ---
            assigned_to, at_err = validate_assigned_user(request.form.get('assigned_to'), lab_id)
            if at_err:
                flash(at_err, 'danger')
                return render_template('commitments/form.html', commitment=commitment, labs=labs,
                                       lab_users=lab_users, action='Chỉnh sửa Cam kết')

            commitment.title = request.form.get('title')
            commitment.description = request.form.get('description')
            commitment.lab_id = lab_id
            commitment.assigned_to = assigned_to
            commitment.start_date = start_date
            commitment.deadline = deadline

        db.session.commit()
        flash(f'Cam kết đã được cập nhật!', 'success')
        return redirect(url_for('commitments.commitments_list'))

    return render_template('commitments/form.html', commitment=commitment, labs=labs,
                           lab_users=lab_users, action='Chỉnh sửa Cam kết')


@bp.route('/commitments/detail/<int:commitment_id>')
@login_required
def commitments_detail(commitment_id):
    commitment = Commitment.query.get_or_404(commitment_id)

    if not current_user.is_admin() and commitment.lab_id != current_user.lab_id:
        flash('Bạn không có quyền xem cam kết này.', 'danger')
        return redirect(url_for('main.dashboard'))

    updates = ProgressUpdate.query.filter_by(commitment_id=commitment_id).order_by(ProgressUpdate.created_at.desc()).all()

    return render_template('commitments/detail.html', commitment=commitment, updates=updates)


@bp.route('/commitments/delete/<int:commitment_id>', methods=['POST'])
@login_required
def commitments_delete(commitment_id):
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Không có quyền'})

    commitment = Commitment.query.get_or_404(commitment_id)
    db.session.delete(commitment)
    db.session.commit()
    return jsonify({'success': True})


@bp.route('/progress/update/<int:commitment_id>', methods=['GET', 'POST'])
@login_required
def progress_update(commitment_id):
    commitment = Commitment.query.get_or_404(commitment_id)

    if not current_user.is_admin() and commitment.lab_id != current_user.lab_id:
        flash('Bạn không có quyền cập nhật cam kết này.', 'danger')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        # --- validate progress ---
        progress_raw = request.form.get('progress')
        new_progress, prog_err = parse_int_field(progress_raw, 'progress')
        if prog_err:
            flash(prog_err, 'danger')
            return render_template('commitments/progress_form.html', commitment=commitment)
        if not (0 <= new_progress <= 100):
            flash('Tiến độ phải nằm trong khoảng từ 0 đến 100.', 'danger')
            return render_template('commitments/progress_form.html', commitment=commitment)

        notes = request.form.get('notes')
        attachment = None

        # Handle file upload — validated before saving to disk.
        if 'attachment' in request.files:
            file = request.files['attachment']
            if file and file.filename:
                safe_name, upload_err = validate_uploaded_file(file)
                if upload_err:
                    flash(upload_err, 'danger')
                    return render_template('commitments/progress_form.html', commitment=commitment)
                # Save only after validation passes; path traversal is impossible because
                # safe_name is a UUID-based string with no path components.
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], safe_name))
                attachment = safe_name

        # Create progress update record
        update = ProgressUpdate(
            commitment_id=commitment_id,
            progress=new_progress,
            notes=notes,
            attachment=attachment,
            created_by=current_user.id
        )
        db.session.add(update)

        # Update commitment progress and status
        commitment.progress = new_progress
        commitment.update_status()

        db.session.commit()
        flash(f'Tiến độ đã được cập nhật lên {new_progress}%!', 'success')
        return redirect(url_for('commitments.commitments_detail', commitment_id=commitment_id))

    return render_template('commitments/progress_form.html', commitment=commitment)
