"""Safe command-line setup, migration, auditing, backup, and restore of storage."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import uuid

import storage


class StorageToolError(RuntimeError):
    pass


def input_path(value: str) -> Path:
    path = Path(os.path.expandvars(value)).expanduser()
    return (path if path.is_absolute() else Path.cwd() / path).resolve()


def check_database(path: Path) -> str:
    if not path.is_file():
        raise StorageToolError(f'Database file not found: {path}')
    try:
        connection = sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True)
        result = connection.execute('PRAGMA integrity_check').fetchone()[0]
        table_count = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
        ).fetchone()[0]
        connection.close()
    except sqlite3.Error as error:
        raise StorageToolError(f'Cannot read SQLite database {path}: {error}') from error
    if result != 'ok':
        raise StorageToolError(f'SQLite integrity check failed for {path}: {result}')
    if table_count == 0:
        raise StorageToolError(f'Database has no tables and looks uninitialized: {path}')
    return f'integrity ok, {table_count} tables'


def copy_database(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f'.{destination.name}.{uuid.uuid4().hex}.tmp')
    try:
        # SQLite's online backup API takes a transactionally consistent snapshot and
        # remains safe while the source database has active readers and writers.
        with closing(sqlite3.connect(str(source), timeout=30)) as source_connection:
            with closing(sqlite3.connect(str(temporary))) as destination_connection:
                source_connection.backup(destination_connection)
        check_database(temporary)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def tree_inventory(folder: Path) -> dict[str, int]:
    return {
        str(path.relative_to(folder)).replace('\\', '/'): path.stat().st_size
        for path in folder.rglob('*') if path.is_file()
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def tree_checksums(folder: Path) -> dict[str, dict[str, int | str]]:
    return {
        str(path.relative_to(folder)).replace('\\', '/'): {
            'size': path.stat().st_size,
            'sha256': file_sha256(path),
        }
        for path in folder.rglob('*') if path.is_file()
    }


def copy_upload_tree(source: Path, destination: Path) -> int:
    if not source.is_dir():
        raise StorageToolError(f'Upload directory not found: {source}')
    if destination.exists():
        if not destination.is_dir():
            raise StorageToolError(f'Upload destination is not a directory: {destination}')
        if any(destination.iterdir()):
            raise StorageToolError(f'Upload destination is not empty: {destination}')

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f'.{destination.name}.{uuid.uuid4().hex}.migrating'
    try:
        shutil.copytree(source, staging)
        source_inventory = tree_inventory(source)
        if tree_inventory(staging) != source_inventory:
            raise StorageToolError('Upload verification failed after copying')
        if destination.exists():
            destination.rmdir()
        staging.rename(destination)
        return len(source_inventory)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def audit_references(database: Path, uploads: Path) -> tuple[int, list[str]]:
    return storage.missing_upload_references(database, uploads)


def update_env(database: Path, uploads: Path, backups: Path) -> None:
    updates = {
        'DATABASE_PATH': str(database),
        'UPLOAD_FOLDER': str(uploads),
        'BACKUP_FOLDER': str(backups),
    }
    original = storage.ENV_FILE.read_text(encoding='utf-8') if storage.ENV_FILE.exists() else ''
    lines = original.splitlines()
    found: set[str] = set()
    rewritten: list[str] = []
    for line in lines:
        key = line.split('=', 1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else ''
        if key in updates:
            rewritten.append(f'{key}={updates[key]}')
            found.add(key)
        else:
            rewritten.append(line)
    if found != set(updates):
        if rewritten and rewritten[-1]:
            rewritten.append('')
        rewritten.append('# Persistent storage locations (managed by storage_tool.py)')
        for key, value in updates.items():
            if key not in found:
                rewritten.append(f'{key}={value}')

    temporary = storage.ENV_FILE.with_name(f'.env.{uuid.uuid4().hex}.tmp')
    temporary.write_text('\n'.join(rewritten).rstrip() + '\n', encoding='utf-8')
    os.replace(temporary, storage.ENV_FILE)


def storage_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    database = input_path(args.database) if args.database else storage.DATABASE_PATH
    uploads = input_path(args.uploads) if args.uploads else storage.UPLOAD_FOLDER
    backups = input_path(args.backups) if args.backups else storage.BACKUP_FOLDER
    return database, uploads, backups


def print_status(_: argparse.Namespace) -> None:
    print(f'Database: {storage.DATABASE_PATH}')
    print(f'Uploads:  {storage.UPLOAD_FOLDER}')
    print(f'Backups:  {storage.BACKUP_FOLDER}')
    print(f'Database source: {"DATABASE_PATH" if storage.DATABASE_PATH_IS_EXPLICIT else "legacy default"}')
    database_status = check_database(storage.DATABASE_PATH)
    print(f'Database check: {database_status}')
    if not storage.UPLOAD_FOLDER.is_dir():
        raise StorageToolError(f'Upload directory not found: {storage.UPLOAD_FOLDER}')
    reference_count, missing = audit_references(storage.DATABASE_PATH, storage.UPLOAD_FOLDER)
    print(f'Upload references: {reference_count}; missing files: {len(missing)}')
    for path in missing[:20]:
        print(f'  MISSING: {path}')
    if len(missing) > 20:
        print(f'  ... and {len(missing) - 20} more')


def configure(args: argparse.Namespace) -> None:
    database, uploads, backups = storage_paths(args)
    check_database(database)
    if not uploads.is_dir():
        raise StorageToolError(f'Upload directory not found: {uploads}')
    references, missing = audit_references(database, uploads)
    if missing:
        raise StorageToolError(
            f'Refusing to configure: {len(missing)} of {references} referenced upload files '
            'are absent. Run status against the intended locations and correct the paths.'
        )
    backups.mkdir(parents=True, exist_ok=True)
    update_env(database, uploads, backups)
    print('Storage configuration saved to .env.')


def migrate(args: argparse.Namespace) -> None:
    database, uploads, backups = storage_paths(args)
    source_database = storage.DATABASE_PATH
    source_uploads = storage.UPLOAD_FOLDER
    check_database(source_database)
    if not source_uploads.is_dir():
        raise StorageToolError(f'Current upload directory not found: {source_uploads}')

    if database != source_database and database.exists():
        raise StorageToolError(f'Refusing to overwrite existing database: {database}')
    if uploads != source_uploads and uploads.exists() and any(uploads.iterdir()):
        raise StorageToolError(f'Refusing to merge into non-empty upload directory: {uploads}')

    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    safety_copy = backups / f'before_migration_{stamp}.db'
    copy_database(source_database, safety_copy)
    print(f'Safety database backup: {safety_copy}')

    if database != source_database:
        copy_database(source_database, database)
        print(f'Database copied: {database}')
    if uploads != source_uploads:
        copied = copy_upload_tree(source_uploads, uploads)
        print(f'Upload files copied and verified: {copied}')

    references, missing = audit_references(database, uploads)
    if missing:
        raise StorageToolError(
            f'Migration copied data, but configuration was not changed because '
            f'{len(missing)} of {references} referenced files are missing.'
        )
    update_env(database, uploads, backups)
    print('Migration verified. New locations saved to .env.')
    print('Original database and uploads were left in place for manual removal after verification.')


def initialize(args: argparse.Namespace) -> None:
    database, uploads, backups = storage_paths(args)
    if database.exists():
        raise StorageToolError(f'Refusing to overwrite existing database: {database}')
    if uploads.exists() and any(uploads.iterdir()):
        raise StorageToolError(f'Refusing to initialize with non-empty uploads: {uploads}')
    database.parent.mkdir(parents=True, exist_ok=True)
    uploads.mkdir(parents=True, exist_ok=True)
    backups.mkdir(parents=True, exist_ok=True)

    environment = os.environ.copy()
    environment.update({
        'DATABASE_PATH': str(database),
        'UPLOAD_FOLDER': str(uploads),
        'BACKUP_FOLDER': str(backups),
        'THEATER_ARCHIVE_ALLOW_NEW_DATABASE': '1',
    })
    result = subprocess.run(
        [sys.executable, str(storage.PROJECT_ROOT / 'init_db.py')],
        cwd=storage.PROJECT_ROOT,
        env=environment,
    )
    if result.returncode != 0:
        raise StorageToolError('Database initialization failed; .env was not changed.')
    check_database(database)
    update_env(database, uploads, backups)
    print('New storage initialized and saved to .env.')


def create_full_backup(destination: Path, database_only: bool = False) -> dict:
    """Create one atomic, verified full-backup directory at an exact location."""
    check_database(storage.DATABASE_PATH)
    if not storage.UPLOAD_FOLDER.is_dir():
        raise StorageToolError(f'Upload directory not found: {storage.UPLOAD_FOLDER}')
    destination = destination.resolve()
    if destination.exists():
        raise StorageToolError(f'Refusing to overwrite existing backup: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f'.{destination.name}_{uuid.uuid4().hex}.tmp'
    published = False
    try:
        with storage.storage_write_lock():
            staging.mkdir()
            backup_database = staging / 'theater_archive.db'
            copy_database(storage.DATABASE_PATH, backup_database)
            upload_files = None
            if not database_only:
                shutil.copytree(storage.UPLOAD_FOLDER, staging / 'uploads')
                source_checksums = tree_checksums(storage.UPLOAD_FOLDER)
                upload_files = tree_checksums(staging / 'uploads')
                if upload_files != source_checksums:
                    raise StorageToolError('Upload checksum verification failed while making backup')
                references, missing = audit_references(backup_database, staging / 'uploads')
                if missing:
                    raise StorageToolError(
                        f'Backup is incomplete: {len(missing)} of {references} referenced files are missing'
                    )
            manifest = {
                'format': 'theater_archive_backup',
                'version': 1,
                'created_at': datetime.now().isoformat(timespec='seconds'),
                'source_database': str(storage.DATABASE_PATH),
                'source_uploads': str(storage.UPLOAD_FOLDER),
                'database': {
                    'file': 'theater_archive.db',
                    'size': backup_database.stat().st_size,
                    'sha256': file_sha256(backup_database),
                },
                'uploads': None if database_only else {
                    'directory': 'uploads',
                    'file_count': len(upload_files),
                    'files': upload_files,
                },
            }
            (staging / 'manifest.json').write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8'
            )
            staging.rename(destination)
            published = True
        if database_only:
            copied_database = destination / manifest['database']['file']
            check_database(copied_database)
            if file_sha256(copied_database) != manifest['database']['sha256']:
                raise StorageToolError('Backup database checksum verification failed')
        else:
            validate_full_backup(destination)
        return manifest
    except Exception:
        if published and destination.exists():
            shutil.rmtree(destination)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def backup(args: argparse.Namespace) -> None:
    backup_root = storage.BACKUP_FOLDER.resolve()
    upload_root = storage.UPLOAD_FOLDER.resolve()
    if backup_root == upload_root or backup_root.is_relative_to(upload_root):
        raise StorageToolError('BACKUP_FOLDER cannot be inside UPLOAD_FOLDER')
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    destination = backup_root / f'archive_{stamp}'
    create_full_backup(destination, database_only=args.database_only)
    print(f'Backup created and verified: {destination}')


def validate_full_backup(backup_directory: Path) -> dict:
    backup_directory = backup_directory.resolve()
    manifest_path = backup_directory / 'manifest.json'
    if not manifest_path.is_file():
        raise StorageToolError(f'Backup manifest not found: {manifest_path}')
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError) as error:
        raise StorageToolError(f'Cannot read backup manifest: {error}') from error
    if manifest.get('format') != 'theater_archive_backup' or manifest.get('version') != 1:
        raise StorageToolError('Unsupported backup format or version')
    if not manifest.get('uploads'):
        raise StorageToolError('This is a database-only backup; full restore requires uploads')

    def backup_member(value, label: str) -> Path:
        if not isinstance(value, str) or not value:
            raise StorageToolError(f'Backup manifest has no {label}')
        member = (backup_directory / value).resolve()
        if not member.is_relative_to(backup_directory):
            raise StorageToolError(f'Backup manifest contains an unsafe {label} path')
        return member

    database_info = manifest.get('database') or {}
    backup_database = backup_member(database_info.get('file'), 'database')
    check_database(backup_database)
    if (backup_database.stat().st_size != database_info.get('size') or
            file_sha256(backup_database) != database_info.get('sha256')):
        raise StorageToolError('Backup database checksum verification failed')

    uploads_info = manifest['uploads']
    backup_uploads = backup_member(uploads_info.get('directory'), 'upload directory')
    if not backup_uploads.is_dir():
        raise StorageToolError(f'Backup upload directory not found: {backup_uploads}')
    actual_files = tree_checksums(backup_uploads)
    if actual_files != uploads_info.get('files'):
        raise StorageToolError('Backup upload checksum verification failed')
    if len(actual_files) != uploads_info.get('file_count'):
        raise StorageToolError('Backup upload file count does not match its manifest')
    references, missing = audit_references(backup_database, backup_uploads)
    if missing:
        raise StorageToolError(
            f'Backup is incomplete: {len(missing)} of {references} referenced files are missing'
        )
    return manifest


def restore(args: argparse.Namespace) -> None:
    backup_directory = input_path(args.backup)
    manifest = validate_full_backup(backup_directory)
    database = input_path(args.database)
    uploads = input_path(args.uploads)
    backups = input_path(args.backups) if args.backups else storage.BACKUP_FOLDER

    if database.exists():
        raise StorageToolError(f'Refusing to overwrite existing database: {database}')
    if uploads.exists() and (not uploads.is_dir() or any(uploads.iterdir())):
        raise StorageToolError(f'Refusing to restore into non-empty upload location: {uploads}')
    if database.is_relative_to(backup_directory) or uploads.is_relative_to(backup_directory):
        raise StorageToolError('Restore destinations cannot be inside the backup being restored')

    backup_database = (backup_directory / manifest['database']['file']).resolve()
    backup_uploads = (backup_directory / manifest['uploads']['directory']).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    uploads.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    staged_database = database.parent / f'.{database.name}.{token}.restoring'
    staged_uploads = uploads.parent / f'.{uploads.name}.{token}.restoring'
    uploads_was_empty_directory = uploads.is_dir()
    uploads_promoted = False
    try:
        copy_database(backup_database, staged_database)
        copied = copy_upload_tree(backup_uploads, staged_uploads)

        restored_files = tree_checksums(staged_uploads)
        if restored_files != manifest['uploads']['files']:
            raise StorageToolError('Restored upload checksum verification failed')
        references, missing = audit_references(staged_database, staged_uploads)
        if missing:
            raise StorageToolError(
                f'Restore is incomplete: {len(missing)} of {references} referenced files are missing'
            )

        # Promote only after the complete staged set has passed every check.  Both final
        # locations were proven absent/empty above, so rollback can safely remove them.
        if database.exists():
            raise StorageToolError(f'Database appeared during restore; refusing to overwrite: {database}')
        if uploads.exists():
            if not uploads.is_dir() or any(uploads.iterdir()):
                raise StorageToolError(
                    f'Upload location changed during restore; refusing to overwrite: {uploads}'
                )
            uploads.rmdir()
        staged_uploads.rename(uploads)
        uploads_promoted = True
        staged_database.rename(database)
    except Exception:
        if uploads_promoted and uploads.exists():
            shutil.rmtree(uploads)
        if uploads_was_empty_directory and not uploads.exists():
            uploads.mkdir(parents=True)
        if database.exists() and not staged_database.exists():
            database.unlink()
        raise
    finally:
        if staged_database.exists():
            staged_database.unlink()
        if staged_uploads.exists():
            shutil.rmtree(staged_uploads)

    if args.activate:
        backups.mkdir(parents=True, exist_ok=True)
        update_env(database, uploads, backups)
    print(f'Full backup restored and verified: database={database}; uploads={uploads}; files={copied}')
    if args.activate:
        print('Restored locations saved to .env. Start the application normally.')
    else:
        print('Configuration was not changed. Use --activate after a test restore when appropriate.')


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description='Configure theater archive storage safely')
    commands = result.add_subparsers(dest='command', required=True)
    status_parser = commands.add_parser('status', help='show paths and audit uploaded files')
    status_parser.set_defaults(handler=print_status)

    for name, help_text, handler in (
        ('configure', 'use already populated locations', configure),
        ('migrate', 'copy current data to new locations and configure them', migrate),
        ('initialize', 'explicitly initialize a new empty archive', initialize),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument('--database', required=(name != 'configure'))
        command.add_argument('--uploads', required=(name != 'configure'))
        command.add_argument('--backups', required=(name != 'configure'))
        command.set_defaults(handler=handler)

    backup_parser = commands.add_parser('backup', help='create a verified backup')
    backup_parser.add_argument('--database-only', action='store_true')
    backup_parser.set_defaults(handler=backup)

    restore_parser = commands.add_parser('restore', help='restore and verify a full backup')
    restore_parser.add_argument('--backup', required=True, help='backup set directory')
    restore_parser.add_argument('--database', required=True, help='new database file path')
    restore_parser.add_argument('--uploads', required=True, help='new empty upload directory')
    restore_parser.add_argument('--backups', help='backup directory to save when activating')
    restore_parser.add_argument('--activate', action='store_true',
                                help='write restored paths to .env after verification')
    restore_parser.set_defaults(handler=restore)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        args.handler(args)
        return 0
    except (StorageToolError, storage.StorageLockTimeout, OSError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
