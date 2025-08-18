import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    # Require MONGO_URI to be provided via environment variables in production
    # This prevents leaking credentials via source control.
    MONGO_URI = os.environ.get('MONGO_URI')
