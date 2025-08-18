from flask import Flask
from config import Config
import os
from app.tinydb_adapter import TinyDatabase

# Initialize TinyDB database (stored in local JSON file)
# Note: for Android Termux, this will be created in the working directory.
db = TinyDatabase(path=os.environ.get('TINYDB_PATH', 'data.json'))

def create_app(config_class=Config):
    from werkzeug.security import generate_password_hash
    # We explicitly set the template_folder to be at the root level
    app = Flask(__name__, 
                template_folder='../templates', 
                static_folder='../static')
    app.config.from_object(config_class)
    app.secret_key = 'supersecretkey-please-change'  # Ganti di production

    # Ensure admin user exists
    admin = db.users.find_one({'username': 'bendahara'})
    if not admin:
        db.users.insert_one({
            'username': 'bendahara',
            # Use PBKDF2 (sha256) to avoid environments lacking hashlib.scrypt (e.g., some Termux builds)
            'password_hash': generate_password_hash('hanyayangberhak', method='pbkdf2:sha256'),
            'role': 'admin',
            'created_at': __import__('datetime').datetime.utcnow()
        })

    # This is where you will register your routes (Blueprints)
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    return app
