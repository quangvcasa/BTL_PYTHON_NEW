from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, send_file, send_from_directory, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from datetime import datetime, timedelta
import os
import io
import uuid
import zipfile
import filetype

from config import Config
from models import db, User, Lab, Commitment, ProgressUpdate

app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Vui lòng đăng nhập để tiếp tục.'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Create upload folder
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ============== ACCESS CONTROL HELPERS ==============

def can_access_lab(lab_id):
    """Admin can access any lab; lab users only their own lab."""
    if current_user.is_admin():
        return True
    return current_user.lab_id is not None and current_user.lab_id == lab_id

def can_access_commitment(commitment):
    """Admin can access any commitment; lab users only commitments of their lab."""
    return can_access_lab(commitment.lab_id)

# ============== VALIDATION HELPERS ==============

ALLOWED_ROLES = {'admin', 'lab'}

def parse_int_field(value, field_name):
    """Parse an integer from a form string. Returns (int_value, error_str)."""
    if value is None or str(value).strip() == '':
        return None, f'Trường "{field_name}" không được để trống.'
    try:
        return int(str(value).strip()), None
    except (ValueError, TypeError):
        return None, f'Trường "{field_name}" phải là số nguyên hợp lệ.'

def parse_date_field(value, field_name):
    """Parse a date string (YYYY-MM-DD). Returns (date, error_str)."""
    if not value or str(value).strip() == '':
        return None, f'Trường "{field_name}" không được để trống.'
    try:
        return datetime.strptime(str(value).strip(), '%Y-%m-%d').date(), None
    except (ValueError, TypeError):
        return None, f'Trường "{field_name}" không đúng định dạng ngày (YYYY-MM-DD).'

def validate_role(role):
    """Ensure role is one of the allowed values. Returns error_str or None."""
    if role not in ALLOWED_ROLES:
        return f'Role không hợp lệ: "{role}". Chỉ chấp nhận: {', '.join(sorted(ALLOWED_ROLES))}.'
    return None

def validate_lab_id(lab_id_raw, required=True):
    """Parse and validate lab_id exists in DB. Returns (int_or_None, error_str)."""
    if lab_id_raw is None or str(lab_id_raw).strip() == '':
        if required:
            return None, 'Trường "lab_id" là bắt buộc.'
        return None, None
    lab_id, err = parse_int_field(lab_id_raw, 'lab_id')
    if err:
        return None, err
    if not Lab.query.get(lab_id):
        return None, f'Lab ID {lab_id} không tồn tại.'
    return lab_id, None

def validate_assigned_user(assigned_to_raw, lab_id):
    """Validate assigned_to user exists and belongs to the given lab.
    Returns (int_or_None, error_str)."""
    raw = assigned_to_raw
    if raw is None or str(raw).strip() == '':
        return None, None  # optional field
    user_id, err = parse_int_field(raw, 'assigned_to')
    if err:
        return None, err
    user = User.query.get(user_id)
    if not user:
        return None, f'Người dùng ID {user_id} không tồn tại.'
    if user.lab_id != lab_id:
        return None, f'Người dùng "{user.username}" không thuộc lab này.'
    return user_id, None

# ============== UPLOAD SECURITY ==============

# Allowed file extensions mapped to their expected MIME types (content-based).
# Only document/image types needed for progress attachments.
ALLOWED_UPLOAD_EXTENSIONS = {
    'pdf':  'application/pdf',
    'png':  'image/png',
    'jpg':  'image/jpeg',
    'jpeg': 'image/jpeg',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}

# OOXML formats (docx, xlsx, pptx) are ZIP archives.  filetype.guess() returns
# 'application/zip' for their magic bytes, not the full OOXML MIME.
# This set lists extensions that need a secondary ZIP-entry verification.
_ZIP_BASED_FORMATS = {
    'docx': 'word/document.xml',
}

def _is_valid_ooxml(file_bytes, required_entry):
    """Return True if file_bytes is a ZIP containing required_entry."""
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            return required_entry in zf.namelist()
    except Exception:
        return False

def validate_uploaded_file(file):
    """Validate an uploaded FileStorage object.

    Checks (in order):
    1. File object exists and has a non-empty filename.
    2. Extension is in the allowlist.
    3. Real MIME type is detected from file bytes (not filename/Content-Type).
       - For standard types: filetype.guess() must match the expected MIME.
       - For OOXML types (.docx): must be a valid ZIP containing the correct entry.
    4. Generates a safe, randomised storage filename (UUID-based).

    Returns:
        (safe_filename: str, error_msg: str | None)
        If error_msg is not None the upload must be rejected.
    """
    if not file or not file.filename:
        return None, None  # no file submitted — caller decides if required

    original_name = secure_filename(file.filename)
    if not original_name:
        return None, 'Tên file không hợp lệ.'

    ext = original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else ''
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        allowed = ', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))
        return None, f'Loại file không được phép. Chỉ chấp nhận: {allowed}.'

    # Read the whole file into memory for detection, then rewind so save() works.
    file_bytes = file.read()
    file.seek(0)

    if ext in _ZIP_BASED_FORMATS:
        # OOXML formats share the PK/ZIP magic header.
        # Verify by inspecting the ZIP central directory for the expected entry.
        required_entry = _ZIP_BASED_FORMATS[ext]
        if not _is_valid_ooxml(file_bytes, required_entry):
            return None, (
                f'File ".{ext}" không hợp lệ hoặc bị giả mạo '
                f'(không tìm thấy đứng từ "{required_entry}" trong ZIP).'
            )
    else:
        # For all other types, detect MIME from magic bytes.
        try:
            kind = filetype.guess(file_bytes[:2048])
            detected_mime = kind.mime if kind else None
        except Exception:
            return None, 'Không thể xác định loại file. Vui lòng thử lại.'

        if detected_mime is None:
            return None, 'Không thể nhận diện loại file từ nội dung.'

        expected_mime = ALLOWED_UPLOAD_EXTENSIONS[ext]
        if detected_mime != expected_mime:
            return None, (
                f'Nội dung file không khớp với đuôi ".{ext}" '
                f'(phát hiện: {detected_mime}).'
            )

    # Safe, unique storage name — never trust the original filename for storage.
    safe_filename = f"{uuid.uuid4().hex}.{ext}"
    return safe_filename, None

# ============== AUTH ROUTES ==============

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            flash('Đăng nhập thành công!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Tên đăng nhập hoặc mật khẩu không đúng.', 'danger')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Đã đăng xuất.', 'info')
    return redirect(url_for('login'))

# ============== DASHBOARD ROUTES ==============

@app.route('/dashboard')
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

@app.route('/my-tasks')
@login_required
def my_tasks():
    """Page showing tasks assigned to current user"""
    if current_user.is_admin():
        flash('Trang này dành cho user Lab.', 'info')
        return redirect(url_for('dashboard'))

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

# ============== LAB ROUTES ==============

@app.route('/labs')
@login_required
def labs_list():
    if not current_user.is_admin():
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('dashboard'))

    labs_list = Lab.query.order_by(Lab.created_at.desc()).all()
    return render_template('labs/list.html', labs=labs_list)

@app.route('/labs/create', methods=['GET', 'POST'])
@login_required
def labs_create():
    if not current_user.is_admin():
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        manager_name = request.form.get('manager_name')
        email = request.form.get('email')

        lab = Lab(name=name, description=description, manager_name=manager_name, email=email)
        db.session.add(lab)
        db.session.commit()

        flash(f'Lab "{name}" đã được tạo thành công!', 'success')
        return redirect(url_for('labs_list'))

    return render_template('labs/form.html', lab=None, action='Tạo Lab mới')

@app.route('/labs/edit/<int:lab_id>', methods=['GET', 'POST'])
@login_required
def labs_edit(lab_id):
    if not current_user.is_admin():
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('dashboard'))

    lab = Lab.query.get_or_404(lab_id)

    if request.method == 'POST':
        lab.name = request.form.get('name')
        lab.description = request.form.get('description')
        lab.manager_name = request.form.get('manager_name')
        lab.email = request.form.get('email')

        db.session.commit()
        flash(f'Lab "{lab.name}" đã được cập nhật!', 'success')
        return redirect(url_for('labs_list'))

    return render_template('labs/form.html', lab=lab, action='Chỉnh sửa Lab')

@app.route('/labs/delete/<int:lab_id>', methods=['POST'])
@login_required
def labs_delete(lab_id):
    if not current_user.is_admin():
        flash('Bạn không có quyền thực hiện thao tác này.', 'danger')
        return redirect(url_for('labs_list'))

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
    return redirect(url_for('labs_list'))

# ============== USER ROUTES (Admin) ==============

@app.route('/users')
@login_required
def users_list():
    if not current_user.is_admin():
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('dashboard'))

    users = User.query.order_by(User.username).all()
    return render_template('users/list.html', users=users)

@app.route('/users/create', methods=['GET', 'POST'])
@login_required
def users_create():
    if not current_user.is_admin():
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('dashboard'))

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
        return redirect(url_for('users_list'))

    return render_template('users/form.html', user=None, labs=labs, action='Tạo User mới')

@app.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
def users_edit(user_id):
    if not current_user.is_admin():
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('dashboard'))

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
        return redirect(url_for('users_list'))

    return render_template('users/form.html', user=user, labs=labs, action='Chỉnh sửa User')

@app.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
def users_delete(user_id):
    if not current_user.is_admin():
        flash('Bạn không có quyền thực hiện thao tác này.', 'danger')
        return redirect(url_for('users_list'))

    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Không thể xóa chính mình.', 'danger')
        return redirect(url_for('users_list'))

    user_name = user.username
    db.session.delete(user)
    db.session.commit()

    flash(f'User "{user_name}" đã được xóa thành công!', 'success')
    return redirect(url_for('users_list'))

# ============== COMMITMENT ROUTES ==============

@app.route('/commitments')
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

@app.route('/commitments/create', methods=['GET', 'POST'])
@login_required
def commitments_create():
    if not current_user.is_admin():
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('dashboard'))

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
        return redirect(url_for('commitments_list'))

    return render_template('commitments/form.html', commitment=None, labs=labs,
                           lab_users=lab_users, action='Tạo Cam kết mới')

@app.route('/commitments/edit/<int:commitment_id>', methods=['GET', 'POST'])
@login_required
def commitments_edit(commitment_id):
    commitment = Commitment.query.get_or_404(commitment_id)

    # Only admin can edit all, lab can only edit their own
    if not current_user.is_admin() and commitment.lab_id != current_user.lab_id:
        flash('Bạn không có quyền chỉnh sửa cam kết này.', 'danger')
        return redirect(url_for('dashboard'))

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
        return redirect(url_for('commitments_list'))

    return render_template('commitments/form.html', commitment=commitment, labs=labs,
                           lab_users=lab_users, action='Chỉnh sửa Cam kết')

@app.route('/commitments/detail/<int:commitment_id>')
@login_required
def commitments_detail(commitment_id):
    commitment = Commitment.query.get_or_404(commitment_id)

    if not current_user.is_admin() and commitment.lab_id != current_user.lab_id:
        flash('Bạn không có quyền xem cam kết này.', 'danger')
        return redirect(url_for('dashboard'))

    updates = ProgressUpdate.query.filter_by(commitment_id=commitment_id).order_by(ProgressUpdate.created_at.desc()).all()

    return render_template('commitments/detail.html', commitment=commitment, updates=updates)

@app.route('/commitments/delete/<int:commitment_id>', methods=['POST'])
@login_required
def commitments_delete(commitment_id):
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Không có quyền'})

    commitment = Commitment.query.get_or_404(commitment_id)
    db.session.delete(commitment)
    db.session.commit()
    return jsonify({'success': True})

# ============== PROGRESS UPDATE ROUTES ==============

@app.route('/progress/update/<int:commitment_id>', methods=['GET', 'POST'])
@login_required
def progress_update(commitment_id):
    commitment = Commitment.query.get_or_404(commitment_id)

    if not current_user.is_admin() and commitment.lab_id != current_user.lab_id:
        flash('Bạn không có quyền cập nhật cam kết này.', 'danger')
        return redirect(url_for('dashboard'))

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
        return redirect(url_for('commitments_detail', commitment_id=commitment_id))

    return render_template('commitments/progress_form.html', commitment=commitment)

# ============== FILE DOWNLOAD ROUTES ==============

@app.route('/uploads/<filename>')
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

# ============== REPORT ROUTES ==============

@app.route('/reports')
@login_required
def reports():
    if not current_user.is_admin():
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('dashboard'))

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

# ============== API ROUTES ==============

@app.route('/api/stats')
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

@app.route('/api/commitments/<int:commitment_id>/timeline')
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

@app.route('/api/labs/<int:lab_id>/users')
@login_required
def api_lab_users(lab_id):
    """Get all lab users for a specific lab (admin only)"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Không có quyền truy cập'}), 403

    users = User.query.filter_by(lab_id=lab_id, role='lab').all()
    return jsonify([{'id': u.id, 'username': u.username} for u in users])

# ============== ERROR HANDLERS ==============

@app.errorhandler(404)
def not_found(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(RequestEntityTooLarge)
def file_too_large(error):
    """Handle uploads that exceed MAX_CONTENT_LENGTH before they reach route logic."""
    flash('File quá lớn. Giới hạn tối đa là 16 MB.', 'danger')
    return redirect(request.referrer or url_for('dashboard')), 413

@app.errorhandler(500)
def server_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

# ============== INIT DATABASE ==============

def ensure_commitments_assigned_to_column():
    """Ensure historic sqlite tables from old schema include the assigned_to column."""
    with app.app_context():
        inspector = db.inspect(db.engine)
        if 'commitments' not in inspector.get_table_names():
            return

        columns = [c['name'] for c in inspector.get_columns('commitments')]
        if 'assigned_to' not in columns:
            try:
                db.session.execute('ALTER TABLE commitments ADD COLUMN assigned_to INTEGER')
                db.session.commit()
                print('Migration: added commitments.assigned_to column')
            except Exception as e:
                db.session.rollback()
                print(f'Migration warning: could not add assigned_to column: {e}')


def init_db():
    """Initialize database with tables and default admin user"""
    with app.app_context():
        db.create_all()
        ensure_commitments_assigned_to_column()

        # Create admin from environment variables only — never from hardcoded defaults.
        admin_username = os.environ.get('ADMIN_USERNAME')
        admin_password = os.environ.get('ADMIN_PASSWORD')
        if admin_username and admin_password:
            if not User.query.filter_by(username=admin_username).first():
                admin = User(username=admin_username, role='admin')
                admin.set_password(admin_password)
                db.session.add(admin)
                db.session.commit()
                print(f'Admin user "{admin_username}" created.')
            else:
                print(f'Admin user "{admin_username}" already exists, skipping.')
        else:
            # No credentials supplied — skip auto-creation silently.
            # Use seed_admin.py to create the first admin manually.
            pass

        # Create sample labs if none exist
        if Lab.query.count() == 0:
            sample_labs = [
                Lab(name='Lab A', description='Phòng thí nghiệm Khoa học Máy tính', manager_name='TS. Nguyễn Văn A', email='labA@ptit.edu.vn'),
                Lab(name='Lab B', description='Phòng thí nghiệm Mạng và Truyền thông', manager_name='ThS. Trần Văn B', email='labB@ptit.edu.vn'),
                Lab(name='Lab C', description='Phòng thí nghiệm Điện tử Viễn thông', manager_name='PGS.TS. Lê Văn C', email='labC@ptit.edu.vn'),
            ]
            for lab in sample_labs:
                db.session.add(lab)
            db.session.commit()
            print(f'{len(sample_labs)} sample labs created')


# Initialize DB when app is created (flask run / WSGI + direct run)
with app.app_context():
    init_db()


if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(debug=debug, host='0.0.0.0', port=5000)