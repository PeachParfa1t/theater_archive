"""Run the weekly/daily backup lifecycle in isolated local folders."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ScheduledBackupIntegrationTest(unittest.TestCase):
    def test_weekly_daily_restore_rotation_and_failed_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = os.environ.copy()
            environment.update({
                'DATABASE_PATH': str(root / 'source-db' / 'archive.db'),
                'UPLOAD_FOLDER': str(root / 'source-uploads'),
                'BACKUP_FOLDER': str(root / 'backup-root'),
                'THEATER_ARCHIVE_ALLOW_NEW_DATABASE': '1',
            })
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name(
                    'scheduled_backup_scenario.py'))],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('SCHEDULED_BACKUP_OK', result.stdout)


if __name__ == '__main__':
    unittest.main()
