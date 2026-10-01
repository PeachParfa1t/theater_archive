"""Full scheduled-backup lifecycle; excluded from direct test discovery."""
from __future__ import annotations

from argparse import Namespace
from datetime import date
import json
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


database = Path(os.environ['DATABASE_PATH'])
uploads = Path(os.environ['UPLOAD_FOLDER'])
backups = Path(os.environ['BACKUP_FOLDER'])
database.parent.mkdir(parents=True)
uploads.mkdir(parents=True)
backups.mkdir(parents=True)


def upload(relative: str, contents: bytes):
    target = uploads / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(contents)


def set_database_state(value: str, add=(), remove=()):
    with sqlite3.connect(database) as connection:
        connection.execute('UPDATE test_state SET value = ? WHERE id = 1', (value,))
        for relative in add:
            connection.execute('INSERT INTO materials (file_path) VALUES (?)', (relative,))
        for relative in remove:
            connection.execute('DELETE FROM materials WHERE file_path = ?', (relative,))


with sqlite3.connect(database) as connection:
    connection.execute(
        'CREATE TABLE materials (id INTEGER PRIMARY KEY, file_path VARCHAR(500))'
    )
    connection.execute(
        'CREATE TABLE test_state (id INTEGER PRIMARY KEY, value VARCHAR(100) NOT NULL)'
    )
    connection.execute('INSERT INTO test_state (id, value) VALUES (1, "day-1")')
    connection.executemany(
        'INSERT INTO materials (file_path) VALUES (?)',
        [('docs/a.txt',), ('docs/b.txt',)],
    )

upload('docs/a.txt', b'A day 1')
upload('docs/b.txt', b'B day 1')

import scheduled_backup


day_1 = date(2026, 9, 1)
day_2 = date(2026, 9, 2)
day_3 = date(2026, 9, 3)
day_4 = date(2026, 9, 4)
next_week = date(2026, 9, 8)

old_set = scheduled_backup.run_scheduled(day_1)
assert old_set.is_dir()
assert scheduled_backup.load_set(old_set, verify_full=True)['_full_date'] == day_1

# Day 2: one modified file and one added file.
upload('docs/a.txt', b'A day 2 modified')
upload('docs/c.txt', b'C day 2 added')
set_database_state('day-2', add=('docs/c.txt',))
scheduled_backup.run_scheduled(day_2)

# Day 3: modify C and physically delete B, with the matching database update.
upload('docs/c.txt', b'C day 3 modified')
(uploads / 'docs/b.txt').unlink()
set_database_state('day-3', remove=('docs/b.txt',))
scheduled_backup.run_scheduled(day_3)

# Day 4: another added file.
upload('docs/d.txt', b'D day 4 added')
set_database_state('day-4', add=('docs/d.txt',))
scheduled_backup.run_scheduled(day_4)

entries = scheduled_backup.daily_entries(old_set)
assert [entry['_backup_date'] for entry in entries] == [day_2, day_3, day_4]
day_2_manifest = json.loads(
    (entries[0]['_directory'] / 'manifest.json').read_text(encoding='utf-8')
)
assert set(day_2_manifest['changes']['added']) == {'docs/c.txt'}
assert set(day_2_manifest['changes']['modified']) == {'docs/a.txt'}
assert day_2_manifest['changes']['deleted'] == []
day_3_manifest = json.loads(
    (entries[1]['_directory'] / 'manifest.json').read_text(encoding='utf-8')
)
assert set(day_3_manifest['changes']['modified']) == {'docs/c.txt'}
assert day_3_manifest['changes']['deleted'] == ['docs/b.txt']


def restored_files(folder: Path) -> dict[str, bytes]:
    return {
        path.relative_to(folder).as_posix(): path.read_bytes()
        for path in folder.rglob('*') if path.is_file()
    }


def verify_restore(target_date: date, expected_state: str, expected_files: dict[str, bytes]):
    root = database.parent.parent / f'restore-{target_date.isoformat()}'
    restored_database = root / 'db' / 'archive.db'
    restored_uploads = root / 'uploads'
    scheduled_backup.restore_point(Namespace(
        date=target_date,
        database=str(restored_database),
        uploads=str(restored_uploads),
        backups=None,
        activate=False,
    ))
    assert restored_files(restored_uploads) == expected_files
    with sqlite3.connect(restored_database) as connection:
        state = connection.execute('SELECT value FROM test_state WHERE id = 1').fetchone()[0]
        references = {
            row[0] for row in connection.execute('SELECT file_path FROM materials')
        }
    assert state == expected_state
    assert references == set(expected_files)


verify_restore(day_1, 'day-1', {
    'docs/a.txt': b'A day 1',
    'docs/b.txt': b'B day 1',
})
verify_restore(day_2, 'day-2', {
    'docs/a.txt': b'A day 2 modified',
    'docs/b.txt': b'B day 1',
    'docs/c.txt': b'C day 2 added',
})
verify_restore(day_3, 'day-3', {
    'docs/a.txt': b'A day 2 modified',
    'docs/c.txt': b'C day 3 modified',
})
verify_restore(day_4, 'day-4', {
    'docs/a.txt': b'A day 2 modified',
    'docs/c.txt': b'C day 3 modified',
    'docs/d.txt': b'D day 4 added',
})

# A deliberately failed validation must leave the complete old generation intact.
original_validator = scheduled_backup.validate_full_backup


def reject_new_full(_directory):
    raise scheduled_backup.ScheduledBackupError('simulated damaged new full backup')


scheduled_backup.validate_full_backup = reject_new_full
try:
    try:
        scheduled_backup.create_weekly_full_locked(next_week)
        raise AssertionError('damaged weekly replacement unexpectedly succeeded')
    except scheduled_backup.ScheduledBackupError as error:
        assert 'simulated damaged' in str(error)
finally:
    scheduled_backup.validate_full_backup = original_validator

assert old_set.is_dir()
assert len(scheduled_backup.daily_entries(old_set)) == 3
assert len(scheduled_backup._set_directories()) == 1

# Once a valid new full backup exists, the old full and all three related dailies go away.
new_set = scheduled_backup.run_scheduled(next_week)
assert new_set.is_dir()
assert not old_set.exists()
assert scheduled_backup._set_directories() == [new_set]
assert scheduled_backup.daily_entries(new_set) == []
scheduled_backup.load_set(new_set, verify_full=True)

verify_restore(next_week, 'day-4', {
    'docs/a.txt': b'A day 2 modified',
    'docs/c.txt': b'C day 3 modified',
    'docs/d.txt': b'D day 4 added',
})

# All source data remained in its own paths throughout every restore.
assert database.is_file()
assert restored_files(uploads) == {
    'docs/a.txt': b'A day 2 modified',
    'docs/c.txt': b'C day 3 modified',
    'docs/d.txt': b'D day 4 added',
}

print('SCHEDULED_BACKUP_OK full=2 daily=3 restores=5 deletion=verified rotation=verified')
