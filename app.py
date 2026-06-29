from flask import Flask, render_template, redirect, url_for, flash, request, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from functools import wraps
import os
import re
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = 'imt-zagursky-archive-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///theater_archive.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Войдите в систему для доступа.'
login_manager.login_message_category = 'warning'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'pdf','doc','docx','jpg','jpeg','png','gif','mp4','avi','mov','mp3','wav','xlsx','xls','ppt','pptx','zip','rar'}

# ===== ROLES =====
ROLE_ADMIN    = 'admin'
ROLE_EDITOR   = 'editor'
ROLE_ZAVLIT   = 'zavlit'
ROLE_MUSIC    = 'music_lib'
ROLE_OBSERVER = 'observer'

# ===== MODELS =====

class Role(db.Model):
    __tablename__ = 'roles'
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(50), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    users        = db.relationship('User', backref='role', lazy=True)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    full_name     = db.Column(db.String(200), nullable=False)
    login         = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role_id       = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, p):
        self.password_hash = generate_password_hash(p)

    def check_password(self, p):
        return check_password_hash(self.password_hash, p)

    @property
    def role_name(self):
        return self.role.name

    def can_edit(self):
        return self.role_name in [ROLE_ADMIN, ROLE_EDITOR, ROLE_ZAVLIT]

    def can_edit_libretto(self):
        return self.role_name in [ROLE_ADMIN, ROLE_ZAVLIT]

    def can_view_libretto(self):
        return self.role_name in [ROLE_ADMIN, ROLE_ZAVLIT]

    def can_manage_music(self):
        return self.role_name in [ROLE_ADMIN, ROLE_MUSIC]

    def can_manage_users(self):
        return self.role_name == ROLE_ADMIN

    def can_view(self):
        return True

class Production(db.Model):
    __tablename__ = 'productions'
    id                    = db.Column(db.Integer, primary_key=True)
    name                  = db.Column(db.String(300), nullable=False)
    status                = db.Column(db.String(20), nullable=False, default='active')
    premiere_year         = db.Column(db.Integer, nullable=False)
    premiere_day          = db.Column(db.Integer)
    premiere_month        = db.Column(db.Integer)
    genre                 = db.Column(db.String(100), nullable=False)
    acts_count            = db.Column(db.Integer)
    literary_basis        = db.Column(db.String(300))
    literary_basis_author = db.Column(db.String(200))
    created_at            = db.Column(db.DateTime, default=datetime.utcnow)

    libretti        = db.relationship('Libretto', backref='production', lazy=True, cascade='all,delete-orphan')
    documents       = db.relationship('Document', backref='production', lazy=True, cascade='all,delete-orphan')
    cast_entries    = db.relationship('CastEntry', backref='production', lazy=True, cascade='all,delete-orphan')
    materials       = db.relationship('Material', backref='production', lazy=True, cascade='all,delete-orphan')
    staging_group   = db.relationship('ProductionDirector', backref='production', lazy=True, cascade='all,delete-orphan')
    authors         = db.relationship('ProductionAuthor', backref='production', lazy=True, cascade='all,delete-orphan')

    MONTHS = {1:'января',2:'февраля',3:'марта',4:'апреля',5:'мая',6:'июня',
              7:'июля',8:'августа',9:'сентября',10:'октября',11:'ноября',12:'декабря'}

    @property
    def status_display(self):
        return 'В показе' if self.status == 'active' else 'Снята'

    @property
    def status_badge(self):
        return 'success' if self.status == 'active' else 'secondary'

    @property
    def premiere_display(self):
        if self.premiere_day and self.premiere_month:
            return f"{self.premiere_day} {self.MONTHS.get(self.premiere_month,'')} {self.premiere_year}"
        return str(self.premiere_year)

    @property
    def music_authors(self):
        return [a.full_name for a in self.authors if a.role == 'music']

    @property
    def libretto_authors(self):
        return [a.full_name for a in self.authors if a.role == 'libretto']

    @property
    def music_authors_display(self):
        return ', '.join(self.music_authors) or '—'

    @property
    def libretto_authors_display(self):
        return ', '.join(self.libretto_authors) or '—'

class ProductionAuthor(db.Model):
    __tablename__ = 'production_authors'
    id            = db.Column(db.Integer, primary_key=True)
    production_id = db.Column(db.Integer, db.ForeignKey('productions.id'), nullable=False)
    full_name     = db.Column(db.String(200), nullable=False)
    role          = db.Column(db.String(20), nullable=False)  # 'music' | 'libretto'

class Libretto(db.Model):
    __tablename__ = 'libretti'
    id            = db.Column(db.Integer, primary_key=True)
    production_id = db.Column(db.Integer, db.ForeignKey('productions.id'), nullable=False)
    file_path     = db.Column(db.String(500))
    file_name     = db.Column(db.String(300))
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    roles         = db.relationship('LibrettoRole', backref='libretto', lazy=True, cascade='all,delete-orphan')

class LibrettoRole(db.Model):
    __tablename__ = 'libretto_roles'
    id           = db.Column(db.Integer, primary_key=True)
    libretto_id  = db.Column(db.Integer, db.ForeignKey('libretti.id'), nullable=False)
    role_name    = db.Column(db.String(200), nullable=False)
    file_path    = db.Column(db.String(500))
    file_name    = db.Column(db.String(300))

class Document(db.Model):
    __tablename__ = 'documents'
    id            = db.Column(db.Integer, primary_key=True)
    production_id = db.Column(db.Integer, db.ForeignKey('productions.id'), nullable=False)
    doc_type      = db.Column(db.String(50), nullable=False)
    file_path     = db.Column(db.String(500), nullable=False)
    file_name     = db.Column(db.String(300), nullable=False)
    title         = db.Column(db.String(300))
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    DOC_TYPES = {'order':'Приказ','contract':'Договор','protocol':'Протокол','act':'Акт','other':'Прочие документы'}

    @property
    def doc_type_display(self):
        return self.DOC_TYPES.get(self.doc_type, self.doc_type)

class Artist(db.Model):
    __tablename__ = 'artists'
    id              = db.Column(db.Integer, primary_key=True)
    full_name       = db.Column(db.String(300), nullable=False)
    title           = db.Column(db.String(200))
    birth_year      = db.Column(db.Integer)
    death_year      = db.Column(db.Integer)
    description     = db.Column(db.Text)
    work_start_year = db.Column(db.Integer)
    work_end_year   = db.Column(db.Integer)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    cast_entries   = db.relationship('CastEntry', backref='artist', lazy=True)
    material_links = db.relationship('MaterialArtist', backref='artist', lazy=True)

    @property
    def life_years(self):
        if self.birth_year and self.death_year:
            return f"{self.birth_year} – {self.death_year}"
        elif self.birth_year:
            return f"р. {self.birth_year}"
        return ''

    @property
    def work_years(self):
        if self.work_start_year and self.work_end_year:
            return f"{self.work_start_year} – {self.work_end_year}"
        elif self.work_start_year:
            return f"с {self.work_start_year}"
        return ''

class CastEntry(db.Model):
    __tablename__ = 'cast_entries'
    id            = db.Column(db.Integer, primary_key=True)
    production_id = db.Column(db.Integer, db.ForeignKey('productions.id'), nullable=False)
    artist_id     = db.Column(db.Integer, db.ForeignKey('artists.id'), nullable=False)
    role_name     = db.Column(db.String(300), nullable=False)
    year_from     = db.Column(db.Integer)
    year_to       = db.Column(db.Integer)

    @property
    def years_display(self):
        if self.year_from and self.year_to and self.year_from != self.year_to:
            return f"{self.year_from} – {self.year_to}"
        elif self.year_from:
            return str(self.year_from)
        return ''

class Director(db.Model):
    __tablename__ = 'directors'
    id         = db.Column(db.Integer, primary_key=True)
    full_name  = db.Column(db.String(300), nullable=False)
    birth_year = db.Column(db.Integer)
    death_year = db.Column(db.Integer)
    position   = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    production_links = db.relationship('ProductionDirector', backref='director', lazy=True)

    POSITIONS = {
        'conductor':     'Дирижёр',
        'director':      'Режиссёр',
        'chorus_master': 'Хормейстер',
        'concertmaster': 'Концертмейстер',
        'ballet_master': 'Балетмейстер',
    }

    @property
    def position_display(self):
        return self.POSITIONS.get(self.position, self.position)

    @property
    def life_years(self):
        if self.birth_year and self.death_year:
            return f"{self.birth_year} – {self.death_year}"
        elif self.birth_year:
            return f"р. {self.birth_year}"
        return ''

class ProductionDirector(db.Model):
    __tablename__ = 'production_directors'
    id            = db.Column(db.Integer, primary_key=True)
    production_id = db.Column(db.Integer, db.ForeignKey('productions.id'), nullable=False)
    director_id   = db.Column(db.Integer, db.ForeignKey('directors.id'), nullable=False)

class Material(db.Model):
    __tablename__ = 'materials'
    id            = db.Column(db.Integer, primary_key=True)
    production_id = db.Column(db.Integer, db.ForeignKey('productions.id'))
    material_type = db.Column(db.String(50), nullable=False)
    file_path     = db.Column(db.String(500))
    file_name     = db.Column(db.String(300))
    url           = db.Column(db.String(1000))
    title         = db.Column(db.String(300))
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    artist_links  = db.relationship('MaterialArtist', backref='material', lazy=True, cascade='all,delete-orphan')

    TYPES = {
        'poster':        'Афиша',
        'sketch':        'Эскиз',
        'photo':         'Фотография',
        'video':         'Видео',
        'media_article': 'Статья СМИ',
        'program':       'Программка',
    }

    @property
    def type_display(self):
        return self.TYPES.get(self.material_type, self.material_type)

    @property
    def type_icon(self):
        icons = {'poster':'📋','sketch':'🎨','photo':'📷','video':'🎬','media_article':'📰','program':'📄'}
        return icons.get(self.material_type, '📁')

    @property
    def is_image(self):
        if self.file_name:
            ext = self.file_name.rsplit('.', 1)[-1].lower()
            return ext in {'jpg','jpeg','png','gif','webp'}
        return False

class MaterialArtist(db.Model):
    __tablename__ = 'material_artists'
    id         = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'), nullable=False)
    artist_id  = db.Column(db.Integer, db.ForeignKey('artists.id'), nullable=False)

# ===== AUTH =====

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role_name not in roles:
                flash('Недостаточно прав для этого действия.', 'danger')
                return redirect(url_for('productions.list_productions'))
            return f(*args, **kwargs)
        return wrapped
    return decorator

def editor_required(f):
    @wraps(f)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.can_edit():
            flash('Недостаточно прав для этого действия.', 'danger')
            return redirect(url_for('productions.list_productions'))
        return f(*args, **kwargs)
    return wrapped

# ===== HELPERS =====

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_file(file):
    """Save an uploaded file under a random ASCII-safe disk name (avoids Windows/filesystem
    issues with non-Latin characters) while preserving the original (e.g. Cyrillic) filename
    for display and downloads."""
    if file and file.filename and allowed_file(file.filename):
        original = file.filename.strip()
        # Strip path separators / control characters but keep Unicode letters (Cyrillic etc.) intact
        original = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', original).strip(' .') or 'file'
        ext = original.rsplit('.', 1)[-1].lower() if '.' in original else ''
        unique = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique))
        return unique, original
    return None, None

def get_or_create_libretto(production_id):
    lib = Libretto.query.filter_by(production_id=production_id).first()
    if not lib:
        lib = Libretto(production_id=production_id)
        db.session.add(lib)
        db.session.flush()
    return lib

def get_or_create_libretto_role(libretto_id, role_name):
    role_name = role_name.strip()
    existing = LibrettoRole.query.filter(
        LibrettoRole.libretto_id == libretto_id,
        db.func.lower(LibrettoRole.role_name) == role_name.lower()
    ).first()
    if existing:
        return existing
    lr = LibrettoRole(libretto_id=libretto_id, role_name=role_name)
    db.session.add(lr)
    db.session.flush()
    return lr

# ===== IMPORT ROUTES =====

from routes.auth        import auth_bp
from routes.productions import productions_bp
from routes.artists     import artists_bp
from routes.libretti    import libretti_bp
from routes.documents   import documents_bp
from routes.materials   import materials_bp
from routes.staging     import staging_bp
from routes.cast        import cast_bp
from routes.admin       import admin_bp
from routes.photobank   import photobank_bp
from routes.material_detail import material_detail_bp
from routes.reports     import reports_bp

app.register_blueprint(auth_bp)
app.register_blueprint(productions_bp)
app.register_blueprint(artists_bp)
app.register_blueprint(libretti_bp)
app.register_blueprint(documents_bp)
app.register_blueprint(materials_bp)
app.register_blueprint(staging_bp)
app.register_blueprint(cast_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(photobank_bp)
app.register_blueprint(material_detail_bp)
app.register_blueprint(reports_bp)

@app.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    download_name = None
    for Model in (Document, Material, Libretto, LibrettoRole):
        row = Model.query.filter_by(file_path=filename).first()
        if row and row.file_name:
            download_name = row.file_name
            break
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, download_name=download_name)

@app.route('/')
@login_required
def index():
    return redirect(url_for('productions.list_productions'))

@app.route('/api/artists')
@login_required
def api_artists():
    from flask import jsonify
    artists = Artist.query.order_by(Artist.full_name).all()
    return jsonify([{'id': a.id, 'label': a.full_name + (f' — {a.title}' if a.title else '')} for a in artists])

@app.route('/api/directors')
@login_required
def api_directors():
    from flask import jsonify
    directors = Director.query.order_by(Director.full_name).all()
    return jsonify([{'id': d.id, 'label': f'{d.full_name} — {d.position_display}'} for d in directors])

@app.route('/api/productions')
@login_required
def api_productions():
    from flask import jsonify
    productions = Production.query.order_by(Production.name).all()
    return jsonify([{'id': p.id, 'label': f'{p.name} ({p.premiere_year})'} for p in productions])

@app.context_processor
def inject_globals():
    return dict(ROLE_ADMIN=ROLE_ADMIN, ROLE_EDITOR=ROLE_EDITOR,
                ROLE_ZAVLIT=ROLE_ZAVLIT, ROLE_MUSIC=ROLE_MUSIC,
                ROLE_OBSERVER=ROLE_OBSERVER)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
