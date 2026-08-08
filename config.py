import os
from dotenv import load_dotenv

load_dotenv()

def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in ('1', 'true', 'yes', 'on')

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    TINYDB_PATH = os.environ.get('TINYDB_PATH') or 'data.json'
    DEBUG = _env_bool('FLASK_DEBUG')
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'bendahara')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
    VIEWER_PASSWORD = os.environ.get('VIEWER_PASSWORD')
    ENABLE_ADMIN_TOOLS = _env_bool('ENABLE_ADMIN_TOOLS')
    WTF_CSRF_TIME_LIMIT = None
