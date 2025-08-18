from flask import Flask
from config import Config
from pymongo import MongoClient
import os

# Initialize MongoDB client
client = MongoClient(Config.MONGO_URI) if Config.MONGO_URI else None
# Determine database: try default from URI, else use MONGO_DB env or fallback name
if client:
    try:
        db = client.get_default_database()
    except Exception:
        db_name = os.environ.get('MONGO_DB', 'bendahara_db')
        db = client[db_name]
else:
    db = None

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
            'password_hash': generate_password_hash('hanyayangberhak'),
            'role': 'admin'
        })

    # This is where you will register your routes (Blueprints)
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    return app
