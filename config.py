"""Application configuration: secrets, Flask config values, and static settings."""
from dotenv import load_dotenv
import os
import secrets

load_dotenv()

SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    print('WARNING: SECRET_KEY not set in environment/.env — generated a random key for this run. '
          'Sessions will be invalidated on restart. Set SECRET_KEY in .env for persistent sessions.')

SQLALCHEMY_DATABASE_URI = 'sqlite:///theater_archive.db'
SQLALCHEMY_TRACK_MODIFICATIONS = False
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
MAX_CONTENT_LENGTH = 200 * 1024 * 1024

ALLOWED_EXTENSIONS = {'pdf','doc','docx','jpg','jpeg','png','gif','mp4','avi','mov','mp3','wav','xlsx','xls','ppt','pptx','zip','rar'}

# ===== ROLES =====
ROLE_ADMIN    = 'admin'
ROLE_EDITOR   = 'editor'
ROLE_ZAVLIT   = 'zavlit'
ROLE_MUSIC    = 'music_lib'
ROLE_OBSERVER = 'observer'
