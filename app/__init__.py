import os
from flask import Flask
from config import Config
from .extensions import db, migrate, login_manager, csrf

def create_app(config_class=Config):
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.config.from_object(config_class)

    # Automatically create instance and upload folders if not exists
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Initialize Flask extensions
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Register User Loader
    from .models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register Blueprints
    from .routes.main import bp as main_bp
    app.register_blueprint(main_bp)

    from .routes.auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    from .routes.users import bp as users_bp
    app.register_blueprint(users_bp)

    from .routes.labs import bp as labs_bp
    app.register_blueprint(labs_bp)

    from .routes.commitments import bp as commitments_bp
    app.register_blueprint(commitments_bp)

    from .routes.reports import bp as reports_bp
    app.register_blueprint(reports_bp)

    from .routes.api import bp as api_bp
    app.register_blueprint(api_bp)

    from .routes.errors import bp as errors_bp
    app.register_blueprint(errors_bp)

    return app
