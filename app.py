from flask import Flask, render_template, redirect, url_for, flash, request, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from functools import wraps
import os

import config

app = Flask(__name__)

app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = config.SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = config.SQLALCHEMY_TRACK_MODIFICATIONS
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Войдите в систему для доступа.'
login_manager.login_message_category = 'warning'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ROLE_ADMIN    = config.ROLE_ADMIN
ROLE_EDITOR   = config.ROLE_EDITOR
ROLE_ZAVLIT   = config.ROLE_ZAVLIT
ROLE_MUSIC    = config.ROLE_MUSIC
ROLE_OBSERVER = config.ROLE_OBSERVER

# ===== MODELS =====

from models import (
    Role, User, Production, ProductionAuthor, Libretto, LibrettoRole,
    Document, Artist, CastEntry, Director, DirectorPosition,
    ProductionDirector, ProductionDirectorPosition, Material,
    MaterialArtist, MaterialDirector,
)

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

from utils import allowed_file, save_file, get_or_create_libretto, get_or_create_libretto_role

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
    return jsonify([{'id': a.id, 'name': a.full_name, 'label': a.full_name + (f' — {a.title}' if a.title else '')} for a in artists])

@app.route('/api/directors')
@login_required
def api_directors():
    from flask import jsonify
    directors = Director.query.order_by(Director.full_name).all()
    return jsonify([{
        'id': d.id,
        'label': f'{d.full_name} — {d.position_display}',
        'positions': [{'code': p.position, 'label': Director.POSITIONS.get(p.position, p.position)} for p in d.positions],
    } for d in directors])

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
