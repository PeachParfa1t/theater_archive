"""Exercise a complete online backup and isolated restore in a child process."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class FullBackupRestoreIntegrationTest(unittest.TestCase):
    def test_online_backup_and_restore_open_record_and_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = os.environ.copy()
            environment.update({
                'DATABASE_PATH': str(root / 'source-db' / 'archive.db'),
                'UPLOAD_FOLDER': str(root / 'source-uploads'),
                'BACKUP_FOLDER': str(root / 'backup-sets'),
                'THEATER_ARCHIVE_ALLOW_NEW_DATABASE': '1',
                'SECRET_KEY': 'full-backup-integration-key',
                'ADMIN_PASSWORD': 'full-backup-integration-password',
            })
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name(
                    'full_backup_restore_scenario.py'))],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('FULL_BACKUP_RESTORE_OK', result.stdout)


if __name__ == '__main__':
    unittest.main()
