"""Run audit-log integration checks in an isolated child process."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class AuditLogIntegrationTest(unittest.TestCase):
    def test_successful_actions_are_logged_and_get_views_are_not(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = os.environ.copy()
            environment.update({
                'DATABASE_PATH': str(root / 'database' / 'archive.db'),
                'UPLOAD_FOLDER': str(root / 'uploads'),
                'BACKUP_FOLDER': str(root / 'backups'),
                'THEATER_ARCHIVE_ALLOW_NEW_DATABASE': '1',
                'SECRET_KEY': 'audit-integration-test-key',
                'ADMIN_PASSWORD': 'audit-integration-admin-password',
            })
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name('audit_log_scenario.py'))],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
