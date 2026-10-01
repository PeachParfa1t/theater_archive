"""Weekly full and daily incremental backups for the theater archive.

The scheduler only needs to invoke ``run`` once per day.  The first run starts a
weekly set, days 2-7 add upload deltas plus an online SQLite snapshot, and a new
verified full set replaces the old set once it is seven days old.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import uuid

import storage
from storage_tool import (
    StorageToolError,
    audit_references,
    check_database,
    copy_database,
    copy_upload_tree,
    create_full_backup,
    file_sha256,
    input_path,
    tree_checksums,
    update_env,
    validate_full_backup,
)


SET_FORMAT = 'theater_archive_scheduled_set'
DAILY_FORMAT = 'theater_archive_daily_increment'
FORMAT_VERSION = 1


class ScheduledBackupError(StorageToolError):
    pass


def _today(value: date | None) -> date:
    return value or date.today()


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('Use date format YYYY-MM-DD') from error


def schedule_root() -> Path:
    backup_root = storage.BACKUP_FOLDER.resolve()
    upload_root = storage.UPLOAD_FOLDER.resolve()
    if backup_root == upload_root or backup_root.is_relative_to(upload_root):
        raise ScheduledBackupError('BACKUP_FOLDER cannot be inside UPLOAD_FOLDER')
    root = backup_root / 'scheduled'
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_manifest(path: Path, value: dict) -> None:
    temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8'
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_manifest(path: Path, label: str) -> dict:
    if not path.is_file():
        raise ScheduledBackupError(f'{label} manifest not found: {path}')
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        raise ScheduledBackupError(f'Cannot read {label} manifest {path}: {error}') from error
    if not isinstance(value, dict):
        raise ScheduledBackupError(f'Invalid {label} manifest: {path}')
    return value


def _member(root: Path, value, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ScheduledBackupError(f'Manifest has no {label}')
    member = (root / value).resolve()
    if not member.is_relative_to(root.resolve()):
        raise ScheduledBackupError(f'Manifest contains an unsafe {label} path')
    return member


def _relative_file(value: str) -> str:
    if not isinstance(value, str) or not value or '\\' in value:
        raise ScheduledBackupError(f'Invalid upload path in manifest: {value!r}')
    relative = PurePosixPath(value)
    if relative.is_absolute() or '..' in relative.parts or relative.name in ('', '.', '..'):
        raise ScheduledBackupError(f'Unsafe upload path in manifest: {value}')
    return relative.as_posix()


def _upload_target(root: Path, relative: str) -> Path:
    relative = _relative_file(relative)
    target = (root / Path(*PurePosixPath(relative).parts)).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ScheduledBackupError(f'Upload path escapes its root: {relative}')
    return target


def _metadata_map(value, label: str) -> dict[str, dict]:
    if not isinstance(value, dict):
        raise ScheduledBackupError(f'{label} must be an object')
    result = {}
    for relative, metadata in value.items():
        relative = _relative_file(relative)
        if (not isinstance(metadata, dict) or
                not isinstance(metadata.get('size'), int) or
                not isinstance(metadata.get('sha256'), str)):
            raise ScheduledBackupError(f'Invalid checksum metadata for {relative}')
        result[relative] = {
            'size': metadata['size'],
            'sha256': metadata['sha256'],
        }
    return result


def _set_directories() -> list[Path]:
    return sorted(
        (path for path in schedule_root().iterdir()
         if path.is_dir() and path.name.startswith('set_')),
        key=lambda path: path.name,
    )


def load_set(set_directory: Path, verify_full: bool = False) -> dict:
    set_directory = set_directory.resolve()
    manifest = _read_manifest(set_directory / 'set_manifest.json', 'scheduled set')
    if manifest.get('format') != SET_FORMAT or manifest.get('version') != FORMAT_VERSION:
        raise ScheduledBackupError(f'Unsupported scheduled set: {set_directory}')
    try:
        full_date = date.fromisoformat(manifest['full_date'])
    except (KeyError, TypeError, ValueError) as error:
        raise ScheduledBackupError(f'Invalid full_date in {set_directory}') from error
    full_directory = _member(set_directory, manifest.get('full_directory'), 'full directory')
    baseline = _metadata_map(manifest.get('baseline_files'), 'baseline_files')
    if verify_full:
        full_manifest = validate_full_backup(full_directory)
        if baseline != full_manifest['uploads']['files']:
            raise ScheduledBackupError('Scheduled baseline does not match its full backup')
    result = dict(manifest)
    result['_directory'] = set_directory
    result['_full_directory'] = full_directory
    result['_full_date'] = full_date
    result['_baseline_files'] = baseline
    if verify_full:
        result['_full_manifest'] = full_manifest
    return result


def active_set() -> tuple[Path, dict] | None:
    candidates = []
    for directory in _set_directories():
        try:
            manifest = load_set(directory)
        except ScheduledBackupError:
            continue
        candidates.append((manifest['_full_date'], directory.name, directory, manifest))
    if not candidates:
        return None
    _full_date, _name, directory, manifest = max(candidates)
    return directory, manifest


def _daily_directories(set_directory: Path) -> list[Path]:
    daily_root = set_directory / 'daily'
    if not daily_root.is_dir():
        return []
    return sorted(
        (path for path in daily_root.iterdir()
         if path.is_dir() and path.name.startswith('day_')),
        key=lambda path: path.name,
    )


def _daily_manifest(directory: Path) -> dict:
    manifest = _read_manifest(directory / 'manifest.json', 'daily backup')
    if manifest.get('format') != DAILY_FORMAT or manifest.get('version') != FORMAT_VERSION:
        raise ScheduledBackupError(f'Unsupported daily backup: {directory}')
    try:
        backup_date = date.fromisoformat(manifest['backup_date'])
    except (KeyError, TypeError, ValueError) as error:
        raise ScheduledBackupError(f'Invalid backup_date in {directory}') from error
    result = dict(manifest)
    result['_directory'] = directory.resolve()
    result['_backup_date'] = backup_date
    return result


def daily_entries(set_directory: Path) -> list[dict]:
    entries = [_daily_manifest(directory) for directory in _daily_directories(set_directory)]
    entries.sort(key=lambda item: (item['_backup_date'], item.get('created_at', '')))
    dates = [entry['_backup_date'] for entry in entries]
    if len(dates) != len(set(dates)):
        raise ScheduledBackupError('A scheduled set contains more than one backup for a day')
    return entries


def validate_incremental(directory: Path, previous_snapshot: dict[str, dict]) -> dict:
    directory = directory.resolve()
    manifest = _daily_manifest(directory)
    database_info = manifest.get('database') or {}
    database = _member(directory, database_info.get('file'), 'daily database')
    check_database(database)
    if (database.stat().st_size != database_info.get('size') or
            file_sha256(database) != database_info.get('sha256')):
        raise ScheduledBackupError(f'Daily database checksum failed: {database}')

    changes = manifest.get('changes') or {}
    added = _metadata_map(changes.get('added'), 'changes.added')
    modified = _metadata_map(changes.get('modified'), 'changes.modified')
    deleted_value = changes.get('deleted')
    if not isinstance(deleted_value, list):
        raise ScheduledBackupError('changes.deleted must be a list')
    deleted = [_relative_file(value) for value in deleted_value]
    if len(deleted) != len(set(deleted)):
        raise ScheduledBackupError('changes.deleted contains duplicates')
    if set(added) & set(modified) or (set(added) | set(modified)) & set(deleted):
        raise ScheduledBackupError('Daily change groups overlap')

    files_directory = _member(directory, manifest.get('files_directory'), 'daily files directory')
    if not files_directory.is_dir():
        raise ScheduledBackupError(f'Daily files directory not found: {files_directory}')
    expected_payload = dict(added)
    expected_payload.update(modified)
    if tree_checksums(files_directory) != expected_payload:
        raise ScheduledBackupError(f'Daily file payload checksum failed: {directory}')

    reconstructed = dict(previous_snapshot)
    for relative in deleted:
        reconstructed.pop(relative, None)
    reconstructed.update(added)
    reconstructed.update(modified)
    snapshot = _metadata_map(manifest.get('snapshot_files'), 'snapshot_files')
    if reconstructed != snapshot:
        raise ScheduledBackupError(f'Daily snapshot chain is inconsistent: {directory}')
    if manifest.get('file_count') != len(snapshot):
        raise ScheduledBackupError(f'Daily file count is inconsistent: {directory}')
    manifest['_snapshot_files'] = snapshot
    manifest['_database'] = database
    manifest['_files_directory'] = files_directory
    manifest['_deleted'] = deleted
    manifest['_added'] = added
    manifest['_modified'] = modified
    return manifest


def validate_chain(set_directory: Path, through: date | None = None,
                   verify_full: bool = True) -> tuple[dict, list[dict]]:
    set_manifest = load_set(set_directory, verify_full=verify_full)
    snapshot = dict(set_manifest['_baseline_files'])
    validated = []
    previous_date = set_manifest['_full_date']
    for entry in daily_entries(set_directory):
        if through is not None and entry['_backup_date'] > through:
            break
        expected_sequence = len(validated) + 1
        if entry.get('sequence') != expected_sequence:
            raise ScheduledBackupError(
                f'Daily sequence is broken at {entry["_directory"]}'
            )
        if entry.get('previous_backup_date') != previous_date.isoformat():
            raise ScheduledBackupError(
                f'Daily predecessor is broken at {entry["_directory"]}'
            )
        checked = validate_incremental(entry['_directory'], snapshot)
        snapshot = checked['_snapshot_files']
        validated.append(checked)
        previous_date = checked['_backup_date']
    return snapshot, validated


def _remove_set(directory: Path, root: Path) -> None:
    directory = directory.resolve()
    root = root.resolve()
    if directory.parent != root or not directory.name.startswith('set_'):
        raise ScheduledBackupError(f'Refusing to remove an unsafe backup path: {directory}')
    shutil.rmtree(directory)


def create_weekly_full(backup_date: date | None = None) -> Path:
    backup_date = _today(backup_date)
    root = schedule_root()
    existing_sets = _set_directories()
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    final = root / f'set_{backup_date.isoformat()}_{stamp}_{uuid.uuid4().hex[:8]}'
    staging = root / f'.{final.name}.tmp'
    published = False
    try:
        staging.mkdir()
        full_directory = staging / 'full'
        full_manifest = create_full_backup(full_directory)
        set_manifest = {
            'format': SET_FORMAT,
            'version': FORMAT_VERSION,
            'created_at': datetime.now().isoformat(timespec='seconds'),
            'full_date': backup_date.isoformat(),
            'full_directory': 'full',
            'baseline_files': full_manifest['uploads']['files'],
        }
        _write_manifest(staging / 'set_manifest.json', set_manifest)
        (staging / 'daily').mkdir()
        load_set(staging)
        staging.rename(final)
        published = True
        load_set(final, verify_full=True)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        if published and final.exists():
            shutil.rmtree(final)
        raise

    # Rotation starts only after the new set has survived a second validation at its
    # final path.  Deleting the directory removes its full and all related dailies.
    for old_set in existing_sets:
        if old_set.resolve() == final.resolve() or not old_set.exists():
            continue
        try:
            _remove_set(old_set, root)
        except OSError as error:
            print(f'WARNING: new set is valid, but old set could not be removed: {error}',
                  file=sys.stderr)
    print(f'Weekly full backup created and verified: {final}')
    return final


def _copy_changed_files(relative_paths: set[str], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for relative in sorted(relative_paths):
        source = _upload_target(storage.UPLOAD_FOLDER, relative)
        target = _upload_target(destination, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def create_daily_increment(backup_date: date | None = None) -> Path:
    backup_date = _today(backup_date)
    selected = active_set()
    if not selected:
        raise ScheduledBackupError('No weekly full backup exists; create one first')
    set_directory, set_manifest = selected
    full_date = set_manifest['_full_date']
    if backup_date <= full_date:
        raise ScheduledBackupError('Daily backup date must be after the weekly full date')
    if (backup_date - full_date).days >= 7:
        raise ScheduledBackupError('The weekly set is seven days old; create a new full backup')

    previous_snapshot, previous_entries = validate_chain(set_directory, verify_full=False)
    if previous_entries and backup_date <= previous_entries[-1]['_backup_date']:
        if backup_date == previous_entries[-1]['_backup_date']:
            print(f'Daily backup already exists for {backup_date.isoformat()}')
            return previous_entries[-1]['_directory']
        raise ScheduledBackupError('Daily backups must be created in chronological order')

    daily_root = set_directory / 'daily'
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    final = daily_root / f'day_{backup_date.isoformat()}_{stamp}_{uuid.uuid4().hex[:8]}'
    staging = daily_root / f'.{final.name}.tmp'
    published = False
    try:
        with storage.storage_write_lock():
            staging.mkdir()
            database = staging / 'theater_archive.db'
            copy_database(storage.DATABASE_PATH, database)
            current_snapshot = tree_checksums(storage.UPLOAD_FOLDER)
            references, missing = audit_references(database, storage.UPLOAD_FOLDER)
            if missing:
                raise ScheduledBackupError(
                    f'Daily backup stopped: {len(missing)} of {references} referenced files are missing'
                )

            previous_names = set(previous_snapshot)
            current_names = set(current_snapshot)
            added_names = current_names - previous_names
            deleted_names = previous_names - current_names
            modified_names = {
                relative for relative in previous_names & current_names
                if previous_snapshot[relative] != current_snapshot[relative]
            }
            _copy_changed_files(added_names | modified_names, staging / 'files')

            manifest = {
                'format': DAILY_FORMAT,
                'version': FORMAT_VERSION,
                'created_at': datetime.now().isoformat(timespec='seconds'),
                'backup_date': backup_date.isoformat(),
                'sequence': len(previous_entries) + 1,
                'previous_backup_date': (
                    previous_entries[-1]['backup_date'] if previous_entries
                    else full_date.isoformat()
                ),
                'database': {
                    'file': 'theater_archive.db',
                    'size': database.stat().st_size,
                    'sha256': file_sha256(database),
                },
                'files_directory': 'files',
                'changes': {
                    'added': {name: current_snapshot[name] for name in sorted(added_names)},
                    'modified': {name: current_snapshot[name] for name in sorted(modified_names)},
                    'deleted': sorted(deleted_names),
                },
                'file_count': len(current_snapshot),
                'snapshot_files': current_snapshot,
            }
            _write_manifest(staging / 'manifest.json', manifest)
            validate_incremental(staging, previous_snapshot)
            staging.rename(final)
            published = True
        validate_incremental(final, previous_snapshot)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        if published and final.exists():
            shutil.rmtree(final)
        raise
    print(
        f'Daily incremental backup created and verified: {final} '
        f'(added={len(added_names)}, modified={len(modified_names)}, deleted={len(deleted_names)})'
    )
    return final


def run_scheduled(backup_date: date | None = None) -> Path:
    backup_date = _today(backup_date)
    root = schedule_root()
    with storage.exclusive_file_lock(root / '.schedule.lock'):
        selected = active_set()
        if not selected:
            return create_weekly_full(backup_date)
        _set_directory, manifest = selected
        age = (backup_date - manifest['_full_date']).days
        if age < 0:
            raise ScheduledBackupError('Requested date is earlier than the active full backup')
        if age >= 7:
            return create_weekly_full(backup_date)
        if age == 0:
            print(f'Weekly full backup already covers {backup_date.isoformat()}')
            return manifest['_directory']
        return create_daily_increment(backup_date)


def create_weekly_full_locked(backup_date: date | None = None) -> Path:
    root = schedule_root()
    with storage.exclusive_file_lock(root / '.schedule.lock'):
        return create_weekly_full(backup_date)


def create_daily_increment_locked(backup_date: date | None = None) -> Path:
    root = schedule_root()
    with storage.exclusive_file_lock(root / '.schedule.lock'):
        return create_daily_increment(backup_date)


def available_restore_points() -> list[tuple[date, str, Path]]:
    points = []
    for set_directory in _set_directories():
        try:
            manifest = load_set(set_directory)
            points.append((manifest['_full_date'], 'full', set_directory))
            for daily in daily_entries(set_directory):
                points.append((daily['_backup_date'], 'daily', daily['_directory']))
        except ScheduledBackupError:
            continue
    return sorted(points, key=lambda item: (item[0], item[1]))


def print_restore_points() -> None:
    root = schedule_root()
    with storage.exclusive_file_lock(root / '.schedule.lock'):
        points = available_restore_points()
    if not points:
        print('No scheduled restore points found.')
        return
    for point_date, kind, path in points:
        print(f'{point_date.isoformat()}  {kind:5}  {path}')


def _select_restore_set(target_date: date) -> tuple[Path, dict]:
    candidates = []
    for set_directory in _set_directories():
        try:
            manifest = load_set(set_directory)
            dates = {manifest['_full_date']}
            dates.update(entry['_backup_date'] for entry in daily_entries(set_directory))
        except ScheduledBackupError:
            continue
        if target_date in dates:
            candidates.append((manifest['_full_date'], set_directory, manifest))
    if not candidates:
        raise ScheduledBackupError(
            f'No verified restore point exists for {target_date.isoformat()}'
        )
    _full_date, directory, manifest = max(candidates, key=lambda item: item[0])
    return directory, manifest


def _apply_increment(staged_uploads: Path, increment: dict) -> None:
    for relative in increment['_deleted']:
        target = _upload_target(staged_uploads, relative)
        if target.exists():
            if not target.is_file():
                raise ScheduledBackupError(f'Cannot delete non-file during restore: {relative}')
            target.unlink()
    for relative in sorted(set(increment['_added']) | set(increment['_modified'])):
        source = _upload_target(increment['_files_directory'], relative)
        target = _upload_target(staged_uploads, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def restore_point(args: argparse.Namespace) -> None:
    target_date = args.date if isinstance(args.date, date) else parse_date(args.date)
    root = schedule_root()
    with storage.exclusive_file_lock(root / '.schedule.lock'):
        set_directory, set_manifest = _select_restore_set(target_date)
        set_manifest = load_set(set_directory, verify_full=True)
        snapshot, increments = validate_chain(
            set_directory, through=target_date, verify_full=False
        )
        if target_date != set_manifest['_full_date']:
            if not increments or increments[-1]['_backup_date'] != target_date:
                raise ScheduledBackupError(f'Incomplete chain for {target_date.isoformat()}')

        database = input_path(args.database)
        uploads = input_path(args.uploads)
        backups = input_path(args.backups) if args.backups else storage.BACKUP_FOLDER
        if database.exists():
            raise ScheduledBackupError(f'Refusing to overwrite existing database: {database}')
        if uploads.exists() and (not uploads.is_dir() or any(uploads.iterdir())):
            raise ScheduledBackupError(
                f'Refusing to restore into non-empty upload location: {uploads}'
            )
        if database.is_relative_to(root) or uploads.is_relative_to(root):
            raise ScheduledBackupError('Restore destinations cannot be inside scheduled backups')

        database.parent.mkdir(parents=True, exist_ok=True)
        uploads.parent.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        staged_database = database.parent / f'.{database.name}.{token}.restoring'
        staged_uploads = uploads.parent / f'.{uploads.name}.{token}.restoring'
        uploads_was_empty_directory = uploads.is_dir()
        uploads_promoted = False
        try:
            full_manifest = set_manifest['_full_manifest']
            full_database = _member(
                set_manifest['_full_directory'], full_manifest['database']['file'],
                'full database',
            )
            full_uploads = _member(
                set_manifest['_full_directory'], full_manifest['uploads']['directory'],
                'full uploads',
            )
            copy_database(full_database, staged_database)
            copy_upload_tree(full_uploads, staged_uploads)

            running_snapshot = dict(set_manifest['_baseline_files'])
            if tree_checksums(staged_uploads) != running_snapshot:
                raise ScheduledBackupError('Restored full upload baseline failed verification')
            for increment in increments:
                _apply_increment(staged_uploads, increment)
                running_snapshot = increment['_snapshot_files']
                if tree_checksums(staged_uploads) != running_snapshot:
                    raise ScheduledBackupError(
                        f'Upload verification failed after {increment["backup_date"]}'
                    )
                copy_database(increment['_database'], staged_database)

            if running_snapshot != snapshot:
                raise ScheduledBackupError('Final upload snapshot does not match the chain')
            references, missing = audit_references(staged_database, staged_uploads)
            if missing:
                raise ScheduledBackupError(
                    f'Restored point is incomplete: {len(missing)} of {references} files are missing'
                )

            if database.exists():
                raise ScheduledBackupError(f'Database appeared during restore: {database}')
            if uploads.exists():
                if not uploads.is_dir() or any(uploads.iterdir()):
                    raise ScheduledBackupError(f'Upload destination changed during restore: {uploads}')
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
        print(
            f'Restore point {target_date.isoformat()} restored and verified: '
            f'database={database}; uploads={uploads}; files={len(snapshot)}'
        )
        if not args.activate:
            print('Configuration was not changed; use --activate only for final recovery.')


def _with_date_parser(command, required: bool = False) -> None:
    command.add_argument(
        '--date', type=parse_date, required=required,
        help='backup/restore date in YYYY-MM-DD format (default: today)',
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description='Weekly full and daily incremental theater archive backups'
    )
    commands = result.add_subparsers(dest='command', required=True)

    run = commands.add_parser('run', help='daily scheduler entry point; chooses full or daily')
    _with_date_parser(run)
    run.set_defaults(handler=lambda args: run_scheduled(args.date))

    full = commands.add_parser('full', help='manually start and rotate to a new weekly set')
    _with_date_parser(full)
    full.set_defaults(handler=lambda args: create_weekly_full_locked(args.date))

    daily = commands.add_parser('daily', help='manually create today\'s daily increment')
    _with_date_parser(daily)
    daily.set_defaults(handler=lambda args: create_daily_increment_locked(args.date))

    listing = commands.add_parser('list', help='list available restore dates')
    listing.set_defaults(handler=lambda _args: print_restore_points())

    restore = commands.add_parser('restore', help='restore a selected available day')
    _with_date_parser(restore, required=True)
    restore.add_argument('--database', required=True, help='new database file path')
    restore.add_argument('--uploads', required=True, help='new empty upload directory')
    restore.add_argument('--backups', help='backup directory to save when activating')
    restore.add_argument('--activate', action='store_true',
                         help='write restored paths to .env after verification')
    restore.set_defaults(handler=restore_point)
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
