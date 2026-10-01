"""Child-process scenario; never imports the developer's configured application."""
from __future__ import annotations

from argparse import Namespace
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import storage_tool
from init_db import init
from app import app, db, Material, Production, User


source_database = Path(os.environ['DATABASE_PATH'])
source_uploads = Path(os.environ['UPLOAD_FOLDER'])
backup_root = Path(os.environ['BACKUP_FOLDER'])
init()

with app.app_context():
    admin_id = User.query.filter_by(login='admin').one().id

client = app.test_client()
with client.session_transaction() as session:
    session['_user_id'] = str(admin_id)
    session['_fresh'] = True

production_name = 'Full backup integration production'
material_title = 'Full backup integration material'
payload = b'full-backup-file\n' + (b'x' * (4 * 1024 * 1024))

response = client.post('/productions/create', data={
    'name': production_name,
    'genre': 'Integration test',
    'premiere_year': '2026',
    'status': 'active',
})
assert response.status_code == 302
response.close()

with app.app_context():
    production = Production.query.filter_by(name=production_name).one()
    production_id = production.id

response = client.post(
    f'/productions/{production_id}/materials/add',
    data={
        'material_type': 'document',
        'title': material_title,
        'mat_file': (BytesIO(payload), 'backup-cycle.pdf'),
    },
    content_type='multipart/form-data',
)
assert response.status_code == 302
response.close()

with app.app_context():
    material = Material.query.filter_by(
        production_id=production_id, title=material_title
    ).one()
    relative_file = material.file_path
assert (source_uploads / relative_file).read_bytes() == payload

# WAL plus a dedicated test table keeps committed writes flowing while SQLite's
# online backup API takes its snapshot.  This database exists only below the test temp dir.
with sqlite3.connect(source_database) as connection:
    journal_mode = connection.execute('PRAGMA journal_mode=WAL').fetchone()[0]
    assert journal_mode.lower() == 'wal'
    connection.execute(
        'CREATE TABLE backup_activity (id INTEGER PRIMARY KEY, note TEXT NOT NULL)'
    )

stop_writer = threading.Event()
writer_ready = threading.Event()
writer_errors: list[Exception] = []
write_count = [0]


def keep_database_busy():
    try:
        with sqlite3.connect(source_database, timeout=5) as connection:
            while not stop_writer.is_set():
                connection.execute(
                    'INSERT INTO backup_activity (note) VALUES (?)',
                    (f'write-{write_count[0]}',),
                )
                connection.commit()
                write_count[0] += 1
                writer_ready.set()
                time.sleep(0.001)
    except Exception as error:  # surfaced in the parent assertion below
        writer_errors.append(error)
        writer_ready.set()


writer = threading.Thread(target=keep_database_busy, daemon=True)
writer.start()
assert writer_ready.wait(10), 'concurrent database writer did not start'
assert not writer_errors, writer_errors
writes_before_backup = write_count[0]
try:
    storage_tool.backup(Namespace(database_only=False))
finally:
    stop_writer.set()
    writer.join(10)
assert not writer.is_alive(), 'concurrent database writer did not stop'
assert not writer_errors, writer_errors
assert write_count[0] > writes_before_backup, 'no database write completed during backup'

backup_sets = list(backup_root.glob('archive_*'))
assert len(backup_sets) == 1, backup_sets
backup_set = backup_sets[0]
manifest = json.loads((backup_set / 'manifest.json').read_text(encoding='utf-8'))
assert manifest['format'] == 'theater_archive_backup'
assert manifest['uploads']['file_count'] >= 1
assert manifest['database']['sha256'] == sha256(
    (backup_set / manifest['database']['file']).read_bytes()
).hexdigest()

restored_database = source_database.parent.parent / 'restored-db' / 'archive.db'
restored_uploads = source_database.parent.parent / 'restored-uploads'
storage_tool.restore(Namespace(
    backup=str(backup_set),
    database=str(restored_database),
    uploads=str(restored_uploads),
    backups=None,
    activate=False,
))

# Restore went elsewhere: the source data and source upload remain intact.
assert restored_database != source_database
assert source_database.is_file()
assert (source_uploads / relative_file).read_bytes() == payload

environment = os.environ.copy()
environment.update({
    'DATABASE_PATH': str(restored_database),
    'UPLOAD_FOLDER': str(restored_uploads),
    'BACKUP_FOLDER': str(source_database.parent.parent / 'restored-backups'),
    'EXPECTED_PRODUCTION': production_name,
    'EXPECTED_MATERIAL': material_title,
    'EXPECTED_FILE_SHA256': sha256(payload).hexdigest(),
})
verification = subprocess.run(
    [sys.executable, str(Path(__file__).with_name('restored_app_scenario.py'))],
    cwd=Path(__file__).resolve().parents[1],
    env=environment,
    capture_output=True,
    text=True,
    timeout=60,
)
assert verification.returncode == 0, verification.stdout + verification.stderr
assert 'RESTORED_APP_OK' in verification.stdout

with app.app_context():
    db.session.remove()
    db.engine.dispose()

print(
    'FULL_BACKUP_RESTORE_OK '
    f'writes_during_backup={write_count[0] - writes_before_backup} '
    f'files={manifest["uploads"]["file_count"]}'
)
