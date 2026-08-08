import logging

from flask import Flask, session
from flask_wtf.csrf import CSRFProtect
from config import Config
from app.tinydb_adapter import TinyDatabase

db = TinyDatabase(path=Config.TINYDB_PATH)
csrf = CSRFProtect()

def create_app(config_class=Config):
    from werkzeug.security import generate_password_hash
    from app.acara_model import AcaraModel

    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')
    app.config.from_object(config_class)
    csrf.init_app(app)

    admin = db.users.find_one({'username': config_class.ADMIN_USERNAME})
    if not admin:
        if config_class.ADMIN_PASSWORD:
            db.users.insert_one({
                'username': config_class.ADMIN_USERNAME,
                'password_hash': generate_password_hash(
                    config_class.ADMIN_PASSWORD, method='pbkdf2:sha256'
                ),
                'role': 'admin',
                'created_at': __import__('datetime').datetime.utcnow()
            })
            logging.warning(
                'Admin user "%s" created from ADMIN_PASSWORD env. Change password after first login.',
                config_class.ADMIN_USERNAME,
            )
        else:
            logging.warning(
                'No admin user found and ADMIN_PASSWORD not set. Set ADMIN_PASSWORD in .env to bootstrap admin.'
            )

    @app.context_processor
    def inject_layout_context():
        from flask import request
        logged_in = 'role' in session
        has_acara = 'acara_id' in session
        endpoint = request.endpoint or ''
        show_main_nav = logged_in and has_acara and endpoint not in ('main.login', 'main.select_acara')
        show_minimal_header = logged_in and not has_acara and endpoint != 'main.login'
        acara_name = None
        if has_acara:
            acara = AcaraModel.get_by_id(session['acara_id'])
            acara_name = acara['nama'] if acara else None
        return {
            'show_main_nav': show_main_nav,
            'show_minimal_header': show_minimal_header,
            'acara_name': acara_name,
            'enable_admin_tools': config_class.ENABLE_ADMIN_TOOLS,
            'viewer_password_required': bool(config_class.VIEWER_PASSWORD),
        }

    from app.routes import main_bp
    app.register_blueprint(main_bp)

    return app
