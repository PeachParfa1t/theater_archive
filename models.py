"""SQLAlchemy models for the theater archive."""
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db
from config import ROLE_ADMIN, ROLE_EDITOR, ROLE_ZAVLIT, ROLE_MUSIC


class Role(db.Model):
    __tablename__ = 'roles'
    id                       = db.Column(db.Integer, primary_key=True)
    name                     = db.Column(db.String(50), unique=True, nullable=False)
    display_name             = db.Column(db.String(100), nullable=False)
    allow_report_generation  = db.Column(db.Boolean, nullable=False, default=True,
                                         server_default='1')
    allow_report_download    = db.Column(db.Boolean, nullable=False, default=True,
                                         server_default='1')
    allow_archive_download   = db.Column(db.Boolean, nullable=False, default=True,
                                         server_default='1')
    users                    = db.relationship('User', backref='role', lazy=True)

    CONFIGURABLE_PERMISSIONS = (
        ('allow_report_generation', 'Формирование отчётов',
         'Доступ к разделу и параметрам формирования отчётов.'),
        ('allow_report_download', 'Скачивание отчётов',
         'Получение сформированных файлов Word и Excel.'),
        ('allow_archive_download', 'Скачивание файлов архива',
         'Открытие и скачивание загруженных документов, изображений и других материалов.'),
    )

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

    def can_generate_reports(self):
        return self.role_name == ROLE_ADMIN or bool(self.role.allow_report_generation)

    def can_download_reports(self):
        return self.role_name == ROLE_ADMIN or bool(self.role.allow_report_download)

    def can_download_archive_files(self):
        return self.role_name == ROLE_ADMIN or bool(self.role.allow_archive_download)

    def can_view(self):
        return True


class AuditLog(db.Model):
    """Immutable, human-readable snapshot of a successful user action."""
    __tablename__ = 'audit_logs'

    id           = db.Column(db.Integer, primary_key=True)
    created_at   = db.Column(db.DateTime, nullable=False, default=datetime.now, index=True)
    # Deliberately not a foreign key: the snapshot must survive a future user deletion.
    user_id      = db.Column(db.Integer, nullable=True, index=True)
    user_name    = db.Column(db.String(200), nullable=False)
    user_login   = db.Column(db.String(100), nullable=False)
    action       = db.Column(db.String(30), nullable=False, index=True)
    object_type  = db.Column(db.String(100), nullable=False, index=True)
    object_id    = db.Column(db.String(100))
    object_label = db.Column(db.String(500), nullable=False)
    details      = db.Column(db.String(1000))

    ACTION_LABELS = {
        'create': 'Создание',
        'update': 'Изменение',
        'delete': 'Удаление',
        'report': 'Формирование отчёта',
    }

    @property
    def action_label(self):
        return self.ACTION_LABELS.get(self.action, self.action)

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
    stage                 = db.Column(db.String(50))
    removal_year          = db.Column(db.Integer)
    age_rating            = db.Column(db.String(10))
    duration_hours        = db.Column(db.Integer)
    duration_minutes      = db.Column(db.Integer)
    has_intermission      = db.Column(db.Boolean, default=False)
    created_at            = db.Column(db.DateTime, default=datetime.utcnow)

    libretti        = db.relationship('Libretto', backref='production', lazy=True, cascade='all,delete-orphan')
    documents       = db.relationship('Document', backref='production', lazy=True, cascade='all,delete-orphan')
    cast_entries    = db.relationship('CastEntry', backref='production', lazy=True, cascade='all,delete-orphan')
    materials       = db.relationship('Material', backref='production', lazy=True, cascade='all,delete-orphan')
    staging_group   = db.relationship('ProductionDirector', backref='production', lazy=True, cascade='all,delete-orphan')
    authors         = db.relationship('ProductionAuthor', backref='production', lazy=True, cascade='all,delete-orphan')
    music_materials = db.relationship('MusicMaterial', backref='production', lazy=True, cascade='all,delete-orphan')

    MONTHS = {1:'января',2:'февраля',3:'марта',4:'апреля',5:'мая',6:'июня',
              7:'июля',8:'августа',9:'сентября',10:'октября',11:'ноября',12:'декабря'}

    STAGES = [
        'Историческая сцена',
        'Основная сцена',
        'Малая сцена',
        'Дом актёра',
        'Музыкальный салон',
    ]

    AGE_RATINGS = ['0+', '6+', '12+', '16+', '18+']

    @property
    def duration_display(self):
        parts = []
        if self.duration_hours:
            parts.append(f'{self.duration_hours} ч')
        if self.duration_minutes:
            parts.append(f'{self.duration_minutes} мин')
        duration = ' '.join(parts)
        intermission = 'с антрактом' if self.has_intermission else 'без антракта'
        return f'{duration}, {intermission}' if duration else intermission

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

    DOC_TYPES = {'order':'Приказ','certificate':'Справка','rao_stats':'Статистика (РАО)','award':'Награда','other':'Прочие документы'}

    @property
    def doc_type_display(self):
        return self.DOC_TYPES.get(self.doc_type, self.doc_type)

class Artist(db.Model):
    __tablename__ = 'artists'
    id              = db.Column(db.Integer, primary_key=True)
    full_name       = db.Column(db.String(300), nullable=False)
    title           = db.Column(db.String(200))  # звание — constrained to RANKS via the form
    position        = db.Column(db.String(200))  # должность — free text, e.g. "Солист балета"
    birth_year      = db.Column(db.Integer)
    death_year      = db.Column(db.Integer)
    description     = db.Column(db.Text)
    work_start_year = db.Column(db.Integer)
    work_end_year   = db.Column(db.Integer)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    cast_entries   = db.relationship('CastEntry', backref='artist', lazy=True)
    material_links = db.relationship('MaterialArtist', backref='artist', lazy=True)

    RANKS = [
        'Заслуженный артист России',
        'Народный артист России',
        'Заслуженный артист РСФСР',
        'Народный артист РСФСР',
        'Народный артист СССР',
    ]

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
        'conductor':          'Дирижёр-постановщик',
        'director':           'Режиссёр-постановщик',
        'chorus_master':      'Хормейстер',
        'concertmaster':      'Концертмейстер',
        'set_designer':       'Художник-постановщик',
        'lighting_designer':  'Художник по свету',
        'costume_designer':   'Художник по костюмам',
        'video_designer':     'Видеохудожник',
        'scenographer':       'Художник-сценограф',
        'choreographer':      'Хореограф-постановщик',
        'theatre_director':   'Директор',
        'chief_director':     'Главный режиссёр',
        'chief_conductor':    'Главный дирижёр',
        'chief_ballet_master':'Главный балетмейстер',
        'lit_drama_head':     'Руководитель литературно-драматургической части',
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

class MusicMaterial(db.Model):
    __tablename__ = 'music_materials'
    id                = db.Column(db.Integer, primary_key=True)
    production_id     = db.Column(db.Integer, db.ForeignKey('productions.id'), nullable=False)
    category          = db.Column(db.String(20), nullable=False)
    file_path         = db.Column(db.String(500), nullable=False)
    original_filename = db.Column(db.String(300), nullable=False)
    description       = db.Column(db.Text)
    upload_date       = db.Column(db.DateTime, default=datetime.utcnow)

    CATEGORIES = {
        'klavir':    'Клавиры',
        'score':     'Партитуры',
        'phonogram': 'Фонограммы',
        'demo':      'Дэмо',
    }

    AUDIO_EXTENSIONS = {'mp3', 'wav', 'flac', 'ogg', 'm4a', 'aac', 'wma', 'mp4'}

    @property
    def category_display(self):
        return self.CATEGORIES.get(self.category, self.category)

    @property
    def is_audio(self):
        if not self.original_filename or '.' not in self.original_filename:
            return False
        return self.original_filename.rsplit('.', 1)[-1].lower() in self.AUDIO_EXTENSIONS


class TourType(db.Model):
    __tablename__ = 'tour_types'
    id   = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)

class Tour(db.Model):
    __tablename__ = 'tours'
    id           = db.Column(db.Integer, primary_key=True)
    city         = db.Column(db.String(200), nullable=False)
    year         = db.Column(db.Integer, nullable=False)
    tour_number  = db.Column(db.Integer)
    tour_type_id = db.Column(db.Integer, db.ForeignKey('tour_types.id'))
    description  = db.Column(db.Text)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    tour_type      = db.relationship('TourType', backref='tours', lazy=True)
    production_links = db.relationship('TourProduction', backref='tour', lazy=True, cascade='all,delete-orphan')
    artist_links    = db.relationship('TourArtist', backref='tour', lazy=True, cascade='all,delete-orphan')
    documents       = db.relationship('TourDocument', backref='tour', lazy=True, cascade='all,delete-orphan')
    materials       = db.relationship('TourMaterial', backref='tour', lazy=True, cascade='all,delete-orphan')

    @property
    def tour_type_name(self):
        return self.tour_type.name if self.tour_type else '—'

    @property
    def tour_number_display(self):
        if not self.tour_number:
            return '—'
        n = self.tour_number
        return f'{n}-я' if n > 1 else f'{n}-я (первая)'

class TourProduction(db.Model):
    __tablename__ = 'tour_productions'
    id            = db.Column(db.Integer, primary_key=True)
    tour_id       = db.Column(db.Integer, db.ForeignKey('tours.id'), nullable=False)
    production_id = db.Column(db.Integer, db.ForeignKey('productions.id'), nullable=False)

    production = db.relationship('Production', backref='tour_links', lazy=True)

class TourArtist(db.Model):
    __tablename__ = 'tour_artists'
    id        = db.Column(db.Integer, primary_key=True)
    tour_id   = db.Column(db.Integer, db.ForeignKey('tours.id'), nullable=False)
    artist_id = db.Column(db.Integer, db.ForeignKey('artists.id'), nullable=False)

    artist = db.relationship('Artist', backref='tour_links', lazy=True)

class TourDocument(db.Model):
    __tablename__ = 'tour_documents'
    id         = db.Column(db.Integer, primary_key=True)
    tour_id    = db.Column(db.Integer, db.ForeignKey('tours.id'), nullable=False)
    doc_type   = db.Column(db.String(50), nullable=False)
    file_path  = db.Column(db.String(500), nullable=False)
    file_name  = db.Column(db.String(300), nullable=False)
    title      = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def doc_type_display(self):
        return Document.DOC_TYPES.get(self.doc_type, self.doc_type)

class TourMaterial(db.Model):
    __tablename__ = 'tour_materials'
    id            = db.Column(db.Integer, primary_key=True)
    tour_id       = db.Column(db.Integer, db.ForeignKey('tours.id'), nullable=False)
    material_type = db.Column(db.String(50), nullable=False)
    file_path     = db.Column(db.String(500))
    file_name     = db.Column(db.String(300))
    url           = db.Column(db.String(1000))
    title         = db.Column(db.String(300))
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def type_display(self):
        return Material.TYPES.get(self.material_type, self.material_type)

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

class Festival(db.Model):
    __tablename__ = 'festivals'
    id        = db.Column(db.Integer, primary_key=True)
    name      = db.Column(db.String(300), nullable=False)
    status_id = db.Column(db.Integer, db.ForeignKey('festival_statuses.id'))

    status   = db.relationship('FestivalStatus', backref='festivals', lazy=True)
    editions = db.relationship('FestivalEdition', backref='festival', lazy=True, cascade='all,delete-orphan')

    @property
    def status_name(self):
        return self.status.name if self.status else '—'

class FestivalStatus(db.Model):
    __tablename__ = 'festival_statuses'
    id   = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)

class FestivalEdition(db.Model):
    __tablename__ = 'festival_editions'
    id          = db.Column(db.Integer, primary_key=True)
    festival_id = db.Column(db.Integer, db.ForeignKey('festivals.id'), nullable=False)
    year        = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    program_entries = db.relationship('FestivalProgramEntry', backref='edition', lazy=True,
                                       cascade='all,delete-orphan',
                                       order_by='FestivalProgramEntry.month, FestivalProgramEntry.day')
    materials       = db.relationship('FestivalMaterial', backref='edition', lazy=True, cascade='all,delete-orphan')
    documents       = db.relationship('FestivalDocument', backref='edition', lazy=True, cascade='all,delete-orphan')

    @property
    def status_name(self):
        """The status now lives on the festival series and applies to every edition."""
        return self.festival.status_name

class FestivalProgramEntry(db.Model):
    __tablename__ = 'festival_program_entries'
    id          = db.Column(db.Integer, primary_key=True)
    edition_id  = db.Column(db.Integer, db.ForeignKey('festival_editions.id'), nullable=False)
    day         = db.Column(db.Integer)
    month       = db.Column(db.Integer)
    time        = db.Column(db.String(20))
    location    = db.Column(db.String(300))
    description = db.Column(db.Text)

    @property
    def date_display(self):
        if self.day and self.month:
            return f'{self.day} {Production.MONTHS.get(self.month, "")}'
        return ''

class FestivalMaterial(db.Model):
    __tablename__ = 'festival_materials'
    id            = db.Column(db.Integer, primary_key=True)
    edition_id    = db.Column(db.Integer, db.ForeignKey('festival_editions.id'), nullable=False)
    material_type = db.Column(db.String(50), nullable=False)
    file_path     = db.Column(db.String(500))
    file_name     = db.Column(db.String(300))
    url           = db.Column(db.String(1000))
    title         = db.Column(db.String(300))
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    TYPES = {
        'poster':        'Афиша',
        'sketch':        'Макеты',
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

class FestivalDocument(db.Model):
    __tablename__ = 'festival_documents'
    id         = db.Column(db.Integer, primary_key=True)
    edition_id = db.Column(db.Integer, db.ForeignKey('festival_editions.id'), nullable=False)
    doc_type   = db.Column(db.String(50), nullable=False)
    file_path  = db.Column(db.String(500), nullable=False)
    file_name  = db.Column(db.String(300), nullable=False)
    title      = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def doc_type_display(self):
        return Document.DOC_TYPES.get(self.doc_type, self.doc_type)


class CompetitionStatus(db.Model):
    __tablename__ = 'competition_statuses'
    id   = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)

class AwardLevel(db.Model):
    __tablename__ = 'award_levels'
    id   = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)

class Competition(db.Model):
    __tablename__ = 'competitions'
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(300), nullable=False)
    year       = db.Column(db.Integer, nullable=False)
    status_id  = db.Column(db.Integer, db.ForeignKey('competition_statuses.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    status           = db.relationship('CompetitionStatus', backref='competitions', lazy=True)
    artist_links     = db.relationship('CompetitionArtist', backref='competition', lazy=True, cascade='all,delete-orphan')
    production_links = db.relationship('CompetitionProduction', backref='competition', lazy=True, cascade='all,delete-orphan')

    @property
    def status_name(self):
        return self.status.name if self.status else '—'

class CompetitionArtist(db.Model):
    __tablename__ = 'competition_artists'
    id                = db.Column(db.Integer, primary_key=True)
    competition_id    = db.Column(db.Integer, db.ForeignKey('competitions.id'), nullable=False)
    artist_id         = db.Column(db.Integer, db.ForeignKey('artists.id'), nullable=False)
    award_level_id    = db.Column(db.Integer, db.ForeignKey('award_levels.id'))
    file_path         = db.Column(db.String(500))
    original_filename = db.Column(db.String(300))

    artist      = db.relationship('Artist', backref='competition_links', lazy=True)
    award_level = db.relationship('AwardLevel', lazy=True)

    @property
    def award_level_name(self):
        return self.award_level.name if self.award_level else '—'

class CompetitionProduction(db.Model):
    __tablename__ = 'competition_productions'
    id                = db.Column(db.Integer, primary_key=True)
    competition_id    = db.Column(db.Integer, db.ForeignKey('competitions.id'), nullable=False)
    production_id     = db.Column(db.Integer, db.ForeignKey('productions.id'), nullable=False)
    award_level_id    = db.Column(db.Integer, db.ForeignKey('award_levels.id'))
    file_path         = db.Column(db.String(500))
    original_filename = db.Column(db.String(300))

    production  = db.relationship('Production', backref='competition_links', lazy=True)
    award_level = db.relationship('AwardLevel', lazy=True)

    @property
    def award_level_name(self):
        return self.award_level.name if self.award_level else '—'
