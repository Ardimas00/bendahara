import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # In production, these MUST be provided via environment variables.
    # load_dotenv() enables local development via a .env file (not committed).
    SECRET_KEY = os.environ.get('SECRET_KEY')
    MONGO_URI = os.environ.get('MONGO_URI')
