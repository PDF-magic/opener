#!/usr/bin/env python3
"""Verify the existing 48-hour ClamAV update-check gate (opener-0269)."""

import importlib.util
import io
from contextlib import redirect_stderr
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("signature_freshness_gate", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class SignatureFreshnessWindowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="signature-freshness-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = self.root / "signatures"
        self.database.mkdir()
        # These are harmless placeholders for testing the *timestamp* contract.
        # The scanner itself remains responsible for interpreting real database files.
        (self.database / "main.cvd").write_bytes(b"synthetic main fixture")
        (self.database / "daily.cld").write_bytes(b"synthetic daily fixture")
        self.stamp = self.database / "last-successful-update"
        self.now = 1_700_000_000.0
        for name, value in (("DATABASE", self.database), ("STAMP", self.stamp)):
            active = patch.object(gate, name, value)
            active.start()
            self.addCleanup(active.stop)

    def verify_timestamp(self, value, *, valid):
        self.stamp.write_text(value, encoding="utf-8")
        with patch.object(gate.time, "time", return_value=self.now):
            if valid:
                self.assertIsNone(gate.check_database())
            else:
                with self.assertRaisesRegex(RuntimeError, "48 hours"):
                    gate.check_database()

    def test_existing_inclusive_48_hour_window(self):
        for age in (0, 1, 47 * 3600, 48 * 3600 - 1, gate.MAX_DATABASE_AGE):
            with self.subTest(age=age):
                self.verify_timestamp(str(self.now - age), valid=True)

        for age in (gate.MAX_DATABASE_AGE + 0.5, gate.MAX_DATABASE_AGE + 1,
                    gate.MAX_DATABASE_AGE + 3600, -0.5, -1):
            with self.subTest(age=age):
                self.verify_timestamp(str(self.now - age), valid=False)
        self.assertEqual(gate.MAX_DATABASE_AGE, 48 * 60 * 60)

    def test_nonfinite_stamps_cannot_bypass_timestamp_comparison(self):
        for stamp in ("nan", "NaN", "+nan", "inf", "-inf", "Infinity", "-Infinity",
                      "1e999", "-1e999"):
            with self.subTest(stamp=stamp):
                self.verify_timestamp(stamp, valid=False)

    def test_missing_and_unparseable_stamps_fail_closed(self):
        with patch.object(gate.time, "time", return_value=self.now):
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                gate.check_database()
        for stamp in ("", "not a timestamp", "2026-10-28T10:00:00Z"):
            with self.subTest(stamp=stamp):
                self.stamp.write_text(stamp)
                with patch.object(gate.time, "time", return_value=self.now):
                    with self.assertRaisesRegex(RuntimeError, "unavailable"):
                        gate.check_database()

    def test_valid_fresh_stamp_still_requires_database_files(self):
        self.stamp.write_text(str(self.now))
        with patch.object(gate.time, "time", return_value=self.now):
            (self.database / "daily.cld").unlink()
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                gate.check_database()
            (self.database / "daily.cld").write_bytes(b"synthetic daily fixture")
            self.assertIsNone(gate.check_database())

    def test_expired_or_nonfinite_stamp_blocks_before_any_scan_or_cache_handoff(self):
        pdf = self.root / "sample.pdf"
        pdf.write_bytes(b"%PDF-1.4\nSynthetic fixture only\n")
        cacheFile = self.root / "clean-cache.sqlite3"
        with patch.object(gate, "CACHE_DB", cacheFile), \
             patch.object(gate.time, "time", return_value=self.now):
            digest = gate.cache_key(gate.fingerprint(pdf), True)
            gate.remember_clean(digest)
            self.assertTrue(gate.cached_clean(digest))

        with patch.object(gate, "watch_parent_lifetime"), \
             patch.object(gate, "scanner_path", return_value="/scanner"), \
             patch.object(gate, "record_scan_request") as record, \
             patch.object(gate, "scan_and_open") as dispatch, \
             patch.object(gate.time, "time", return_value=self.now):
            for stamp in (str(self.now - gate.MAX_DATABASE_AGE - 1), "nan",
                          str(self.now + 1)):
                with self.subTest(stamp=stamp):
                    self.stamp.write_text(stamp)
                    with redirect_stderr(io.StringIO()):
                        self.assertEqual(gate.main([str(pdf)]), 1)
                    dispatch.assert_not_called()
                    record.assert_not_called()

            self.stamp.write_text(str(self.now - gate.MAX_DATABASE_AGE))
            with redirect_stderr(io.StringIO()):
                self.assertEqual(gate.main([str(pdf)]), 0)
            dispatch.assert_called_once_with(str(pdf), "/scanner")
            record.assert_called_once()


if __name__ == "__main__":
    unittest.main()
