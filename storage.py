"""Resolve and validate the archive's persistent storage locations.

Database rows contain paths relative to ``UPLOAD_FOLDER``.  Keeping that rule in
one place lets an administrator move the whole upload tree without rewriting the
database.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / '.env'
LEGACY_DATABASE_PATH = PROJECT_ROOT / 'instance' / 'theater_archive.db'
LEGACY_UPLOAD_FOLDER = PROJECT_ROOT / 'uploads'
DEFAULT_BACKUP_FOLDER = PROJECT_ROOT / 'backups'
FILE_REFERENCE_TABLES = (
    'libretti', 'libretto_roles', 'documents', 'materials', 'music_materials',
    'tour_documents', 'tour_materials', 'festival_documents', 'festival_materials',
    'competition_artists', 'competition_productions',
)

# Loading a specific file makes startup independent of the service's working directory.
load_dotenv(ENV_FILE)


class StorageConfigurationError(RuntimeError):
    """Raised when configured storage could cause data to be silently lost."""


def _configured_path(variable: str, default: Path) -> tuple[Path, bool]:
    raw = os.environ.get(variable, '').strip()
    if not raw:
        return default.resolve(), False
    expanded = Path(os.path.expandvars(raw)).expanduser()
    if not expanded.is_absolute():
        expanded = PROJECT_ROOT / expanded
    return expanded.resolve(), True


DATABASE_PATH, DATABASE_PATH_IS_EXPLICIT = _configured_path(
    'DATABASE_PATH', LEGACY_DATABASE_PATH
)
UPLOAD_FOLDER, UPLOAD_FOLDER_IS_EXPLICIT = _configured_path(
    'UPLOAD_FOLDER', LEGACY_UPLOAD_FOLDER
)
BACKUP_FOLDER, BACKUP_FOLDER_IS_EXPLICIT = _configured_path(
    'BACKUP_FOLDER', DEFAULT_BACKUP_FOLDER
)


def sqlite_uri(path: Path) -> str:
    """Return an absolute SQLAlchemy SQLite URI on Windows and POSIX."""
    return f"sqlite:///{path.as_posix()}"


def _is_sqlite_database(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 100:
        return False
    with path.open('rb') as database_file:
        return database_file.read(16) == b'SQLite format 3\x00'


def missing_upload_references(database: Path, uploads: Path) -> tuple[int, list[str]]:
    """Return the number of distinct stored file paths and those absent on disk."""
    references: set[str] = set()
    connection = sqlite3.connect(f'file:{database.as_posix()}?mode=ro', uri=True)
    try:
        existing_tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        for table in FILE_REFERENCE_TABLES:
            if table not in existing_tables:
                continue
            for (file_path,) in connection.execute(
                f'SELECT file_path FROM {table} '
                'WHERE file_path IS NOT NULL AND file_path != ""'
            ):
                references.add(str(file_path).replace('\\', '/').lstrip('/'))
    finally:
        connection.close()
    def is_present(relative_path: str) -> bool:
        path = Path(relative_path)
        if path.is_absolute() or '..' in path.parts:
            return False
        return (uploads / path).is_file()

    missing = sorted(path for path in references if not is_present(path))
    return len(references), missing


def ensure_runtime_storage() -> None:
    """Fail early on a typo/new empty location instead of creating empty storage.

    A fresh database is allowed at the historical default path so the existing
    ``python init_db.py`` workflow remains compatible.  For an explicitly configured
    path, creation must be requested through ``storage_tool.py initialize``.
    """
    allow_new = os.environ.get('THEATER_ARCHIVE_ALLOW_NEW_DATABASE') == '1'

    if DATABASE_PATH.exists():
        if not _is_sqlite_database(DATABASE_PATH):
            raise StorageConfigurationError(
                f'DATABASE_PATH points to a file that is not a valid SQLite database: '
                f'{DATABASE_PATH}'
            )
    elif DATABASE_PATH_IS_EXPLICIT and not allow_new:
        raise StorageConfigurationError(
            f'The configured database does not exist: {DATABASE_PATH}. '
            'Use "python storage_tool.py migrate ..." for existing data or '
            '"python storage_tool.py initialize ..." for a deliberately new archive.'
        )

    if not DATABASE_PATH.parent.exists():
        if DATABASE_PATH_IS_EXPLICIT and not allow_new:
            raise StorageConfigurationError(
                f'The configured database directory does not exist: {DATABASE_PATH.parent}'
            )
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    for label, path, is_explicit in (
        ('UPLOAD_FOLDER', UPLOAD_FOLDER, UPLOAD_FOLDER_IS_EXPLICIT),
        ('BACKUP_FOLDER', BACKUP_FOLDER, BACKUP_FOLDER_IS_EXPLICIT),
    ):
        if path.exists() and not path.is_dir():
            raise StorageConfigurationError(f'{label} is not a directory: {path}')
        if not path.exists():
            if is_explicit and not allow_new:
                raise StorageConfigurationError(
                    f'The configured {label} does not exist: {path}. '
                    'Create/configure it with storage_tool.py before starting the server.'
                )
            path.mkdir(parents=True, exist_ok=True)

    # A manually edited, but valid-looking, empty upload directory must not make all old
    # links disappear without an explicit diagnostic.  The setup utility performs this
    # same audit before writing .env.
    if ((DATABASE_PATH_IS_EXPLICIT or UPLOAD_FOLDER_IS_EXPLICIT)
            and _is_sqlite_database(DATABASE_PATH)):
        reference_count, missing = missing_upload_references(DATABASE_PATH, UPLOAD_FOLDER)
        if missing:
            sample = ', '.join(missing[:3])
            raise StorageConfigurationError(
                f'UPLOAD_FOLDER is missing {len(missing)} of {reference_count} files '
                f'referenced by the database (for example: {sample}). '
                'Correct the path or run storage_tool.py migrate; the server was not started.'
            )
