"""Regression checks for verified storage migration."""
from __future__ import annotations

from argparse import Namespace
import os
import sqlite3
from pathlib import Path
import tempfile
import unittest

import storage
import storage_tool


class StorageMigrationTest(unittest.TestCase):
    def test_explicit_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing_database = root / 'database' / 'missing.db'
            uploads = root / 'uploads'
            backups = root / 'backups'
            uploads.mkdir()
            backups.mkdir()
            old_values = (
                storage.DATABASE_PATH,
                storage.DATABASE_PATH_IS_EXPLICIT,
                storage.UPLOAD_FOLDER,
                storage.UPLOAD_FOLDER_IS_EXPLICIT,
                storage.BACKUP_FOLDER,
                storage.BACKUP_FOLDER_IS_EXPLICIT,
            )
            try:
                allow_new = os.environ.pop('THEATER_ARCHIVE_ALLOW_NEW_DATABASE', None)
                storage.DATABASE_PATH = missing_database
                storage.DATABASE_PATH_IS_EXPLICIT = True
                storage.UPLOAD_FOLDER = uploads
                storage.UPLOAD_FOLDER_IS_EXPLICIT = True
                storage.BACKUP_FOLDER = backups
                storage.BACKUP_FOLDER_IS_EXPLICIT = True
                with self.assertRaises(storage.StorageConfigurationError):
                    storage.ensure_runtime_storage()
                self.assertFalse(missing_database.exists())
            finally:
                if allow_new is not None:
                    os.environ['THEATER_ARCHIVE_ALLOW_NEW_DATABASE'] = allow_new
                (
                    storage.DATABASE_PATH,
                    storage.DATABASE_PATH_IS_EXPLICIT,
                    storage.UPLOAD_FOLDER,
                    storage.UPLOAD_FOLDER_IS_EXPLICIT,
                    storage.BACKUP_FOLDER,
                    storage.BACKUP_FOLDER_IS_EXPLICIT,
                ) = old_values

    def test_migration_copies_database_uploads_and_updates_environment_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_database = root / 'old' / 'archive.db'
            source_uploads = root / 'old-uploads'
            destination_database = root / 'new-db' / 'archive.db'
            destination_uploads = root / 'new-uploads'
            destination_backups = root / 'new-backups'
            environment_file = root / '.env'

            source_database.parent.mkdir(parents=True)
            source_uploads.mkdir()
            relative_file = Path('photos') / '1' / 'existing.jpg'
            (source_uploads / relative_file.parent).mkdir(parents=True)
            (source_uploads / relative_file).write_bytes(b'existing contents')
            connection = sqlite3.connect(source_database)
            connection.execute(
                'CREATE TABLE materials (id INTEGER PRIMARY KEY, file_path VARCHAR(500))'
            )
            connection.execute(
                'INSERT INTO materials (file_path) VALUES (?)', (relative_file.as_posix(),)
            )
            connection.commit()
            connection.close()

            old_values = (
                storage.DATABASE_PATH,
                storage.UPLOAD_FOLDER,
                storage.BACKUP_FOLDER,
                storage.ENV_FILE,
            )
            try:
                storage.DATABASE_PATH = source_database
                storage.UPLOAD_FOLDER = source_uploads
                storage.BACKUP_FOLDER = root / 'old-backups'
                storage.ENV_FILE = environment_file
                storage_tool.migrate(Namespace(
                    database=str(destination_database),
                    uploads=str(destination_uploads),
                    backups=str(destination_backups),
                ))
            finally:
                (
                    storage.DATABASE_PATH,
                    storage.UPLOAD_FOLDER,
                    storage.BACKUP_FOLDER,
                    storage.ENV_FILE,
                ) = old_values

            self.assertEqual(
                (destination_uploads / relative_file).read_bytes(), b'existing contents'
            )
            self.assertEqual(storage_tool.check_database(destination_database).split(',')[0],
                             'integrity ok')
            references, missing = storage_tool.audit_references(
                destination_database, destination_uploads
            )
            self.assertEqual((references, missing), (1, []))
            settings = environment_file.read_text(encoding='utf-8')
            self.assertIn(f'DATABASE_PATH={destination_database}', settings)
            self.assertIn(f'UPLOAD_FOLDER={destination_uploads}', settings)
            self.assertIn(f'BACKUP_FOLDER={destination_backups}', settings)
            self.assertTrue(any(destination_backups.glob('before_migration_*.db')))
            self.assertTrue(source_database.exists())
            self.assertTrue((source_uploads / relative_file).exists())


if __name__ == '__main__':
    unittest.main()
