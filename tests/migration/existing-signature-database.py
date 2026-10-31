#!/usr/bin/env python3
"""opener-0936: find preexisting ClamAV signatures without altering them."""

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "existing_signature_database.py"
spec = importlib.util.spec_from_file_location("existing_signature_database", SOURCE)
detector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(detector)


class ExistingSignatureDatabaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="opener-migration-signatures-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.database = self.root / "install" / "signatures"

    def put(self, name, content=b"fixture signatures\n"):
        self.database.mkdir(parents=True, exist_ok=True)
        file = self.database / name
        file.write_bytes(content)
        return file

    def run_detector(self):
        return subprocess.run(
            [sys.executable, str(SOURCE), str(self.database)],
            capture_output=True, text=True, check=False,
        )

    def test_fresh_install_is_missing_and_does_not_create_directory(self):
        self.assertEqual(detector.detect_existing_signature_database(self.database), "missing")
        self.assertFalse(self.database.exists())
        result = self.run_detector()
        self.assertEqual(result.returncode, 0)
        self.assertIn("No existing", result.stdout)
        self.assertFalse(self.database.exists())

    def test_all_supported_main_daily_formats_detect_existing_without_stamp(self):
        for main_ext, daily_ext in ((".cvd", ".cvd"), (".cvd", ".cld"),
                                    (".cld", ".cvd"), (".cld", ".cld")):
            with self.subTest(main=main_ext, daily=daily_ext):
                self.database.mkdir(parents=True, exist_ok=True)
                for item in self.database.iterdir():
                    item.unlink()
                self.put("main" + main_ext)
                self.put("daily" + daily_ext)
                original = {p.name: p.read_bytes() for p in self.database.iterdir()}
                self.assertEqual(detector.detect_existing_signature_database(self.database), "existing")
                result = self.run_detector()
                self.assertEqual(result.returncode, 0)
                self.assertIn("validation is still required", result.stdout)
                self.assertEqual(original, {p.name: p.read_bytes() for p in self.database.iterdir()})

    def test_partial_empty_or_ambiguous_database_is_not_reported_complete(self):
        self.database.mkdir(parents=True)
        self.assertEqual(detector.detect_existing_signature_database(self.database), "incomplete")
        self.put("main.cvd")
        self.assertEqual(detector.detect_existing_signature_database(self.database), "incomplete")
        self.put("daily.cld", b"")
        self.assertEqual(detector.detect_existing_signature_database(self.database), "incomplete")
        self.put("daily.cld")
        self.put("main.cld")
        self.assertEqual(detector.detect_existing_signature_database(self.database), "incomplete")
        self.assertIn("incomplete", self.run_detector().stdout)

    def test_unsafe_directory_and_entries_fail_closed_without_following_links(self):
        outside = self.root / "private"
        outside.write_bytes(b"private data")
        self.database.parent.mkdir()
        self.database.symlink_to(outside)
        self.assertEqual(detector.detect_existing_signature_database(self.database), "unsafe")
        self.database.unlink()
        self.database.mkdir()
        self.put("main.cvd")
        (self.database / "daily.cvd").symlink_to(outside)
        result = self.run_detector()
        self.assertEqual(result.returncode, 1)
        self.assertIn("unsafe", result.stderr)
        self.assertNotIn(str(self.root), result.stderr)
        self.assertEqual(outside.read_bytes(), b"private data")
        (self.database / "daily.cvd").unlink()
        (self.database / "daily.cvd").mkdir()
        self.assertEqual(detector.detect_existing_signature_database(self.database), "unsafe")

    def test_unreadable_location_is_not_assumed_absent(self):
        with patch.object(detector.os, "lstat", side_effect=PermissionError):
            self.assertEqual(detector.detect_existing_signature_database(self.database), "unsafe")

    def test_installer_runs_detection_before_mutation_and_ci_tracks_it(self):
        installer = (ROOT / "install-allow-and-open.sh").read_text()
        marker = 'python3 "$script_dir/existing_signature_database.py" "$install_dir/signatures"'
        self.assertIn(marker, installer)
        self.assertLess(installer.index(marker), installer.index('mkdir -p "$install_dir/signatures"'))
        self.assertIn('bash "$install_dir/update-malware-signatures.sh"', installer)
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("python3 tests/migration/existing-signature-database.py -v", ci)
        self.assertIn("bash -n install-allow-and-open.sh", ci)


if __name__ == "__main__":
    unittest.main()
