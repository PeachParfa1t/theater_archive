"""Run the web integration scenario in a process isolated from imported config."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ConfiguredStorageIntegrationTest(unittest.TestCase):
    def test_create_upload_and_open_existing_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = os.environ.copy()
            environment.update({
                'DATABASE_PATH': str(root / 'database' / 'archive.db'),
                'UPLOAD_FOLDER': str(root / 'uploaded-files'),
                'BACKUP_FOLDER': str(root / 'backup-files'),
                'THEATER_ARCHIVE_ALLOW_NEW_DATABASE': '1',
                'SECRET_KEY': 'integration-test-key',
                'ADMIN_PASSWORD': 'integration-test-password',
            })
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name('storage_web_scenario.py'))],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
