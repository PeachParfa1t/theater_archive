"""Run role-permission checks against an isolated legacy-format database."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class RolePermissionIntegrationTest(unittest.TestCase):
    def test_visibility_direct_access_and_existing_special_rules(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = os.environ.copy()
            environment.update({
                'DATABASE_PATH': str(root / 'database' / 'archive.db'),
                'UPLOAD_FOLDER': str(root / 'uploads'),
                'BACKUP_FOLDER': str(root / 'backups'),
                'THEATER_ARCHIVE_ALLOW_NEW_DATABASE': '1',
                'SECRET_KEY': 'role-permission-integration-key',
                'ADMIN_PASSWORD': 'role-permission-admin-password',
            })
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name(
                    'role_permissions_scenario.py'))],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('ROLE_PERMISSIONS_OK', result.stdout)


if __name__ == '__main__':
    unittest.main()
