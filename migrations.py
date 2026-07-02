"""Individual, additive-only schema migrations. Safe to re-run — each ignores errors caused
by the change already having been applied (e.g. column/table already exists)."""
import sqlalchemy as sa
from app import app, db


def _add_columns_if_missing(alter_statements):
    with db.engine.connect() as conn:
        for stmt in alter_statements:
            try:
                conn.execute(sa.text(stmt))
                conn.commit()
            except Exception:
                pass  # column already exists — safe to ignore


def add_literary_basis_columns_to_productions():
    _add_columns_if_missing([
        "ALTER TABLE productions ADD COLUMN literary_basis VARCHAR(300)",
        "ALTER TABLE productions ADD COLUMN literary_basis_author VARCHAR(200)",
    ])


def add_year_range_columns_to_cast_entries():
    _add_columns_if_missing([
        "ALTER TABLE cast_entries ADD COLUMN year_from INTEGER",
        "ALTER TABLE cast_entries ADD COLUMN year_to INTEGER",
    ])


def relax_director_position_notnull():
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


def create_new_tables():
    """Creates any brand-new tables (e.g. production_authors, director_positions,
    material_directors) that don't exist yet. Never touches existing tables/data."""
    db.create_all()


def migrate_director_positions_data():
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
