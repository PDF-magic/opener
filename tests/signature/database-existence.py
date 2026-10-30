#!/usr/bin/env python3
"""Verify Standard's installed main/daily signature files before any PDF opens."""

from contextlib import redirect_stderr
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("scan_and_open", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class SignatureDatabaseExistenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="opener-signatures-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.database = self.root / "signatures"
        self.database.mkdir()
        self.stamp = self.database / "last-successful-update"
        self.stamp.write_text(str(time.time()), encoding="ascii")
        self.document = self.root / "document.pdf"
        self.document.write_bytes(b"%PDF-1.4\nTest only\n")
        db = patch.object(gate, "DATABASE", self.database)
        stamp = patch.object(gate, "STAMP", self.stamp)
        db.start()
        stamp.start()
        self.addCleanup(db.stop)
        self.addCleanup(stamp.stop)

    def add_signature(self, name, suffix=".cvd"):
        file = self.database / (name + suffix)
        file.write_bytes(b"ClamAV-VDB:mock:test\n")
        return file

    def test_missing_main_or_daily_is_incomplete_even_with_fresh_stamp(self):
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            gate.check_database()
        self.add_signature("main")
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            gate.check_database()
        (self.database / "main.cvd").unlink()
        self.add_signature("daily", ".cld")
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            gate.check_database()

    def test_nonempty_regular_files_accept_either_supported_clamav_extension(self):
        for main_ext, daily_ext in (
            (".cvd", ".cvd"), (".cvd", ".cld"),
            (".cld", ".cvd"), (".cld", ".cld"),
        ):
            with self.subTest(main=main_ext, daily=daily_ext):
                for candidate in self.database.glob("*.c[vl]d"):
                    candidate.unlink()
                self.add_signature("main", main_ext)
                self.add_signature("daily", daily_ext)
                self.assertIsNone(gate.check_database())
        self.assertEqual(len(list(self.database.glob("*.c[vl]d"))), 2)

    def test_directory_empty_file_and_symlinks_cannot_impersonate_signatures(self):
        self.add_signature("main")
        daily = self.database / "daily.cvd"
        daily.mkdir()
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            gate.check_database()
        daily.rmdir()
        daily.touch()
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            gate.check_database()
        daily.unlink()
        outside = self.root / "outside.cvd"
        outside.write_bytes(b"ClamAV-VDB:external")
        daily.symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            gate.check_database()
        daily.unlink()
        daily.symlink_to(self.root / "missing.cvd")
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            gate.check_database()

    def test_invalid_main_is_not_masked_by_valid_daily_or_alternate_name(self):
        self.add_signature("daily", ".cld")
        (self.database / "main.cvd").mkdir()
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            gate.check_database()
        (self.database / "main.cld").touch()
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            gate.check_database()
        self.add_signature("main", ".cld")
        self.assertIsNone(gate.check_database())

    def test_database_existence_is_required_before_scanner_and_cache_handoff(self):
        # A fresh timestamp with bogus signature paths must never allow even
        # an existing clean-cache hit to proceed to quarantine or launch.
        (self.database / "main.cvd").mkdir()
        self.add_signature("daily")
        with patch.object(gate, "scanner_path", return_value="/mock/clamscan"), \
                patch.object(gate, "scan_and_open") as scan, \
                patch.object(gate, "remove_quarantine") as remove, \
                redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(gate.main([str(self.document)]), 1)
        scan.assert_not_called()
        remove.assert_not_called()
        self.assertIn("signature database is incomplete", stderr.getvalue())
        self.assertNotIn(str(self.root), stderr.getvalue())

    def test_existing_freshness_and_missing_stamp_are_still_fail_closed(self):
        self.add_signature("main")
        self.add_signature("daily")
        self.stamp.unlink()
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            gate.check_database()
        self.stamp.write_text(str(time.time() - 49 * 60 * 60))
        with self.assertRaisesRegex(RuntimeError, "48 hours"):
            gate.check_database()
        self.stamp.write_text(str(time.time()))
        self.assertIsNone(gate.check_database())


if __name__ == "__main__":
    unittest.main()
