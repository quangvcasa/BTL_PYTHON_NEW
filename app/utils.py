import os
import io
import uuid
import zipfile
import filetype
from datetime import datetime
from flask_login import current_user
from werkzeug.utils import secure_filename
from flask import current_app

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
        return f'Role không hợp lệ: "{role}". Chỉ chấp nhận: {", ".join(sorted(ALLOWED_ROLES))}.'
    return None

def validate_lab_id(lab_id_raw, required=True):
    """Parse and validate lab_id exists in DB. Returns (int_or_None, error_str)."""
    if lab_id_raw is None or str(lab_id_raw).strip() == '':
        if required:
            return None, 'Trường "lab_id" là bắt buộc.'
        return None, None
    try:
        from .models import Lab  # defer import to avoid circular imports if any
        lab_id = int(str(lab_id_raw).strip())
        lab = Lab.query.get(lab_id)
        if not lab:
            return None, 'Lab không tồn tại.'
        return lab_id, None
    except ValueError:
        return None, 'ID Lab phải là số.'

def validate_assigned_to(user_id_raw, lab_id, required=False):
    """Parse and validate that user belongs to the given lab. Returns (int_or_None, error_str)."""
    if user_id_raw is None or str(user_id_raw).strip() == '':
        if required:
            return None, 'Trường "Người phụ trách" là bắt buộc.'
        return None, None
    try:
        from .models import User
        user_id = int(str(user_id_raw).strip())
        user = User.query.get(user_id)
        if not user:
            return None, 'User phụ trách không tồn tại.'
        if user.role != 'admin' and user.lab_id != lab_id:
            return None, 'User phụ trách phải thuộc Lab này.'
        return user_id, None
    except ValueError:
        return None, 'ID người phụ trách phải là một số.'

# ============== FILE UPLOAD SECURITY FIX ==============

def get_safe_docx_type(file_bytes):
    """Safely introspect a generic ZIP (application/zip) to see if it is actually a valid DOCX."""
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes), 'r') as zip_ref:
            if '[Content_Types].xml' in zip_ref.namelist() and 'word/document.xml' in zip_ref.namelist():
                return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    except zipfile.BadZipFile:
        pass
    return None

def validate_uploaded_file(file, field_name):
    """
    Reads the file to determine its MIME type safely using python-filetype.
    Returns (safe_filename, content_bytes, error_MSG)
    """
    if not file or file.filename == '':
        return None, None, None

    filename = secure_filename(file.filename)
    file_bytes = file.read()
    file.seek(0)
    
    if len(file_bytes) == 0:
        return None, None, f'File "{filename}" bị rỗng.'
    
    kind = filetype.guess(file_bytes)
    
    if kind is None:
        return None, None, f'Không thể xác định định dạng thực sự của file "{filename}". File bị từ chối.'

    mime_type = kind.mime
    
    if mime_type == 'application/zip':
        docx_mime = get_safe_docx_type(file_bytes)
        if docx_mime:
            mime_type = docx_mime
    
    ALLOWED_MIMES = {
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'image/jpeg',
        'image/png'
    }
    
    if mime_type not in ALLOWED_MIMES:
        return None, None, f'Định dạng file bị cấm: {mime_type}. Chỉ cho phép tải lên Document, Image, PDF.'
    
    ext = os.path.splitext(filename)[1].lower()
    unique_filename = f"{uuid.uuid4().hex}{ext}_{filename}"
    
    return unique_filename, file_bytes, None
