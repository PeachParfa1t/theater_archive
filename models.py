"""SQLAlchemy models for the theater archive."""
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db
from config import ROLE_ADMIN, ROLE_EDITOR, ROLE_ZAVLIT, ROLE_MUSIC


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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    production_links = db.relationship('ProductionDirector', backref='director', lazy=True)
    positions        = db.relationship('DirectorPosition', backref='director', lazy=True, cascade='all,delete-orphan')

    POSITIONS = {
        'conductor':         'Дирижёр',
        'director':          'Режиссёр',
        'chorus_master':     'Хормейстер',
        'concertmaster':     'Концертмейстер',
        'ballet_master':     'Балетмейстер',
        'set_designer':      'Художник-постановщик',
        'lighting_designer': 'Художник по свету',
        'costume_designer':  'Художник по костюмам',
        'video_designer':    'Видеохудожник',
        'scenographer':      'Художник-сценограф',
        'choreographer':     'Хореограф-постановщик',
    }

    @property
    def position_codes(self):
        return [p.position for p in self.positions]

    @property
    def position_display(self):
        names = [self.POSITIONS.get(p.position, p.position) for p in self.positions]
        return ', '.join(names) if names else '—'

    @property
    def life_years(self):
        if self.birth_year and self.death_year:
            return f"{self.birth_year} – {self.death_year}"
        elif self.birth_year:
            return f"р. {self.birth_year}"
        return ''

class DirectorPosition(db.Model):
    __tablename__ = 'director_positions'
    id          = db.Column(db.Integer, primary_key=True)
    director_id = db.Column(db.Integer, db.ForeignKey('directors.id'), nullable=False)
    position    = db.Column(db.String(50), nullable=False)

class ProductionDirector(db.Model):
    __tablename__ = 'production_directors'
    id            = db.Column(db.Integer, primary_key=True)
    production_id = db.Column(db.Integer, db.ForeignKey('productions.id'), nullable=False)
    director_id   = db.Column(db.Integer, db.ForeignKey('directors.id'), nullable=False)

    positions = db.relationship('ProductionDirectorPosition', backref='production_director', lazy=True, cascade='all,delete-orphan')

    @property
    def position_display(self):
        """Positions chosen specifically for this production; falls back to showing all of the
        director's positions if none were picked (covers links created before this feature)."""
        names = [Director.POSITIONS.get(p.position, p.position) for p in self.positions]
        return ', '.join(names) if names else self.director.position_display

class ProductionDirectorPosition(db.Model):
    __tablename__ = 'production_director_positions'
    id                      = db.Column(db.Integer, primary_key=True)
    production_director_id = db.Column(db.Integer, db.ForeignKey('production_directors.id'), nullable=False)
    position                = db.Column(db.String(50), nullable=False)

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

    artist_links   = db.relationship('MaterialArtist', backref='material', lazy=True, cascade='all,delete-orphan')
    director_links = db.relationship('MaterialDirector', backref='material', lazy=True, cascade='all,delete-orphan')

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

class MaterialDirector(db.Model):
    __tablename__ = 'material_directors'
    id          = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'), nullable=False)
    director_id = db.Column(db.Integer, db.ForeignKey('directors.id'), nullable=False)

    director = db.relationship('Director', lazy=True)
