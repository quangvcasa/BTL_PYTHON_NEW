import os

class Config:
    # SECRET_KEY must be set in the environment. No insecure fallback.
    _secret = os.environ.get('SECRET_KEY')
    if not _secret:
        raise RuntimeError(
            "[FATAL] Environment variable SECRET_KEY is not set. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    SECRET_KEY = _secret

    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASEDIR, 'instance', 'ptit_lab_progress.db').replace('\\', '/')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {'check_same_thread': False}
    }
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    # Hard server-side upload size limit; Flask rejects larger requests with 413.
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB