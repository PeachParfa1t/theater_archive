"""Helper functions: file uploads and libretto lookup/creation helpers."""
import os
import re
import uuid

from app import app, db
from config import ALLOWED_EXTENSIONS
from models import Libretto, LibrettoRole


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Maps a material_type token to its top-level folder name under uploads/
MATERIAL_TYPE_FOLDERS = {
    'photo':         'photos',
    'video':         'videos',
    'poster':        'posters',
    'sketch':        'sketches',
    'program':       'programs',
    'media_article': 'media_articles',
    'document':      'documents',
    'libretto':      'libretti',
}

def save_file(file, material_type=None, production_id=None):
    """Save an uploaded file under a random ASCII-safe disk name (avoids Windows/filesystem
    issues with non-Latin characters) while preserving the original (e.g. Cyrillic) filename
    for display and downloads.

    Files are organized under uploads/<type-folder>/<production_id>/, e.g. photos/3/<uuid>.jpg.
    Materials with no production (Фотобанк) go to uploads/photobank/. If material_type is not
    recognized, the file falls back to the flat uploads/ root (old behavior) for compatibility.
    Returns (relative_path, original_filename) — relative_path includes the subfolder, e.g.
    "photos/3/<uuid>.jpg", and is what gets stored in the DB / passed to uploaded_file().
    """
    if not (file and file.filename and allowed_file(file.filename)):
        return None, None

    original = file.filename.strip()
    # Strip path separators / control characters but keep Unicode letters (Cyrillic etc.) intact
    original = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', original).strip(' .') or 'file'
    ext = original.rsplit('.', 1)[-1].lower() if '.' in original else ''
    unique = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex

    folder = MATERIAL_TYPE_FOLDERS.get(material_type)
    if folder and production_id:
        subfolder = f'{folder}/{production_id}'
    elif folder:
        subfolder = 'photobank'  # material with no production (e.g. Фотобанк uploads)
    else:
        subfolder = ''  # unknown/unspecified type — flat uploads/ root, old behavior

    target_dir = os.path.join(app.config['UPLOAD_FOLDER'], subfolder) if subfolder else app.config['UPLOAD_FOLDER']
    os.makedirs(target_dir, exist_ok=True)
    file.save(os.path.join(target_dir, unique))

    relative_path = f'{subfolder}/{unique}' if subfolder else unique
    return relative_path, original

def get_or_create_libretto(production_id):
    lib = Libretto.query.filter_by(production_id=production_id).first()
    if not lib:
        lib = Libretto(production_id=production_id)
        db.session.add(lib)
        db.session.flush()
    return lib

def get_or_create_libretto_role(libretto_id, role_name):
    role_name = role_name.strip()
    target = role_name.lower()
    # Compare case-insensitively in Python, not via SQL lower(): SQLite's built-in lower()
    # only folds ASCII a-z and leaves Cyrillic/other non-ASCII text untouched, so a SQL-side
    # comparison would almost never match Cyrillic role names and silently create duplicates.
    for existing in LibrettoRole.query.filter_by(libretto_id=libretto_id).all():
        if existing.role_name.strip().lower() == target:
            return existing
    lr = LibrettoRole(libretto_id=libretto_id, role_name=role_name)
    db.session.add(lr)
    db.session.flush()
    return lr
