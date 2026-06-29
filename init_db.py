"""Run on every startup. Safely migrates schema (additive only, never drops data) then seeds defaults."""
import os
import sqlalchemy as sa
from app import app, db, Role, User, Production, Artist, Director, DirectorPosition, ROLE_ADMIN

def migrate_schema():
    """Add new columns/tables to an existing DB without touching existing data."""
    with app.app_context():
        alter_statements = [
            "ALTER TABLE productions ADD COLUMN literary_basis VARCHAR(300)",
            "ALTER TABLE productions ADD COLUMN literary_basis_author VARCHAR(200)",
            "ALTER TABLE cast_entries ADD COLUMN year_from INTEGER",
            "ALTER TABLE cast_entries ADD COLUMN year_to INTEGER",
        ]
        with db.engine.connect() as conn:
            for stmt in alter_statements:
                try:
                    conn.execute(sa.text(stmt))
                    conn.commit()
                except Exception:
                    pass  # column already exists — safe to ignore
        _relax_director_position_notnull()
        db.create_all()  # creates any brand-new tables (e.g. production_authors, director_positions, material_directors)
        _migrate_director_positions()

def _relax_director_position_notnull():
    """The legacy directors.position column was originally NOT NULL. The app no longer writes
    to it (positions now live in director_positions), so new inserts omit it — which SQLite
    would otherwise reject. SQLite has no ALTER COLUMN, so relaxing the constraint requires the
    standard rebuild-and-copy technique. All existing data (including the old position values)
    is copied over unchanged; only the constraint is relaxed."""
    with db.engine.connect() as conn:
        info = conn.execute(sa.text("PRAGMA table_info(directors)")).fetchall()
        position_col = next((c for c in info if c[1] == 'position'), None)
        if not position_col or position_col[3] == 0:
            return  # column doesn't exist yet, or is already nullable — nothing to do
        conn.execute(sa.text("""
            CREATE TABLE directors_new (
                id INTEGER PRIMARY KEY,
                full_name VARCHAR(300) NOT NULL,
                birth_year INTEGER,
                death_year INTEGER,
                position VARCHAR(100),
                created_at DATETIME
            )
        """))
        conn.execute(sa.text(
            "INSERT INTO directors_new (id, full_name, birth_year, death_year, position, created_at) "
            "SELECT id, full_name, birth_year, death_year, position, created_at FROM directors"
        ))
        conn.execute(sa.text("DROP TABLE directors"))
        conn.execute(sa.text("ALTER TABLE directors_new RENAME TO directors"))
        conn.commit()

def _migrate_director_positions():
    """One-time data migration: copy each director's legacy single `position` column value
    into the new director_positions table (multiple positions per director). The old
    `position` column is left in place, untouched and simply unused going forward."""
    with db.engine.connect() as conn:
        try:
            rows = conn.execute(sa.text(
                "SELECT id, position FROM directors WHERE position IS NOT NULL AND position != ''"
            )).fetchall()
        except Exception:
            return  # legacy 'position' column doesn't exist on a fresh DB — nothing to migrate
        for director_id, position in rows:
            already_migrated = conn.execute(sa.text(
                "SELECT COUNT(*) FROM director_positions WHERE director_id = :did"
            ), {'did': director_id}).scalar()
            if not already_migrated:
                conn.execute(sa.text(
                    "INSERT INTO director_positions (director_id, position) VALUES (:did, :pos)"
                ), {'did': director_id, 'pos': position})
        conn.commit()

def init():
    with app.app_context():
        migrate_schema()

        roles_data = [
            (ROLE_ADMIN,    'Администратор'),
            ('editor',      'Редактор архива'),
            ('zavlit',      'Завлит'),
            ('music_lib',   'Нотный библиотекарь'),
            ('observer',    'Наблюдатель'),
        ]
        for name, display in roles_data:
            if not Role.query.filter_by(name=name).first():
                db.session.add(Role(name=name, display_name=display))
        db.session.commit()

        if not User.query.filter_by(login='admin').first():
            admin_password = os.environ.get('ADMIN_PASSWORD')
            if not admin_password:
                admin_password = 'admin123'
                print("WARNING: ADMIN_PASSWORD not set in environment/.env — using default password "
                      "'admin123' for the admin account. Set ADMIN_PASSWORD in .env for a secure password.")
            admin_role = Role.query.filter_by(name=ROLE_ADMIN).first()
            admin = User(full_name='Администратор', login='admin', role_id=admin_role.id)
            admin.set_password(admin_password)
            db.session.add(admin)
            db.session.commit()
            print("Admin created: login=admin")

        # Demo data — only inserted on a completely fresh database
        if Production.query.count() == 0:
            prods = [
                Production(name='Евгений Онегин', status='active', premiere_year=1998,
                           premiere_day=15, premiere_month=9,
                           genre='Опера', acts_count=3,
                           literary_basis='Роман в стихах «Евгений Онегин»',
                           literary_basis_author='А.С. Пушкин'),
                Production(name='Лебединое озеро', status='active', premiere_year=2005,
                           premiere_day=20, premiere_month=3,
                           genre='Балет', acts_count=4),
                Production(name='Свадьба Фигаро', status='removed', premiere_year=1987,
                           genre='Опера-буфф', acts_count=4,
                           literary_basis='Комедия «Безумный день, или Женитьба Фигаро»',
                           literary_basis_author='П. Бомарше'),
                Production(name='Весёлая вдова', status='active', premiere_year=2019,
                           premiere_day=1, premiere_month=11,
                           genre='Оперетта', acts_count=3),
            ]
            for p in prods:
                db.session.add(p)
            db.session.flush()
            from app import ProductionAuthor
            db.session.add(ProductionAuthor(production_id=prods[0].id, full_name='П.И. Чайковский', role='music'))
            db.session.add(ProductionAuthor(production_id=prods[0].id, full_name='М.И. Чайковский', role='libretto'))
            db.session.add(ProductionAuthor(production_id=prods[0].id, full_name='К.С. Шиловский', role='libretto'))
            db.session.add(ProductionAuthor(production_id=prods[1].id, full_name='П.И. Чайковский', role='music'))
            db.session.add(ProductionAuthor(production_id=prods[2].id, full_name='В.А. Моцарт', role='music'))
            db.session.add(ProductionAuthor(production_id=prods[2].id, full_name='Л. да Понте', role='libretto'))
            db.session.add(ProductionAuthor(production_id=prods[3].id, full_name='Ф. Легар', role='music'))

        if Artist.query.count() == 0:
            artists = [
                Artist(full_name='Петров Александр Иванович',
                       title='Заслуженный артист России',
                       birth_year=1965, work_start_year=1990,
                       description='Ведущий тенор театра'),
                Artist(full_name='Иванова Мария Сергеевна',
                       title='Народная артистка России',
                       birth_year=1958, death_year=2020,
                       work_start_year=1980, work_end_year=2015,
                       description='Прима-балерина, лауреат государственных премий'),
                Artist(full_name='Сидоров Николай Петрович',
                       birth_year=1980, work_start_year=2005,
                       description='Баритон'),
            ]
            for a in artists:
                db.session.add(a)

        if Director.query.count() == 0:
            seed_directors = [
                ('Загурский Николай Михайлович', ['director'], 1940, 2010),
                ('Орлов Виктор Семёнович', ['conductor'], 1955, None),
                ('Белова Ольга Николаевна', ['ballet_master', 'choreographer'], 1968, None),
            ]
            for name, position_codes, birth_year, death_year in seed_directors:
                d = Director(full_name=name, birth_year=birth_year, death_year=death_year)
                db.session.add(d)
                db.session.flush()
                for code in position_codes:
                    db.session.add(DirectorPosition(director_id=d.id, position=code))

        db.session.commit()
        print("Database ready (existing data preserved).")

if __name__ == '__main__':
    init()
