#!/usr/bin/env python3
"""opener-0393: no scan or cached-clean handoff after signature invalidation."""
from contextlib import redirect_stderr
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("signature_batch_gate", ROOT / "scan-and-open.py")
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class MandatorySignatureGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="signature-batch-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.signatures = self.root / "signatures"
        self.signatures.mkdir()
        self.stamp = self.signatures / "last-successful-update"
        self.stamp.write_text(str(time.time()))
        (self.signatures / "main.cvd").write_bytes(b"main-fixture")
        (self.signatures / "daily.cld").write_bytes(b"daily-fixture")
        self.pdfs = []
        for index in (1, 2):
            pdf = self.root / ("sample%d.pdf" % index)
            pdf.write_bytes(b"%PDF-1.4\nSynthetic offline test fixture\n")
            self.pdfs.append(str(pdf))
        for name, value in (("DATABASE", self.signatures), ("STAMP", self.stamp)):
            active = patch.object(scanner, name, value)
            active.start()
            self.addCleanup(active.stop)

    def run_batch(self, change):
        calls = []
        def dispatch(item, engine):
            calls.append(item)
            if len(calls) == 1:
                change()
        with patch.object(scanner, "scanner_path", return_value="/test-clamscan"), \
             patch.object(scanner, "watch_parent_lifetime"), \
             patch.object(scanner, "record_scan_request") as records, \
             patch.object(scanner, "scan_and_open", side_effect=dispatch) as scans, \
             redirect_stderr(io.StringIO()) as errors:
            result = scanner.main(self.pdfs)
        return result, calls, scans, records, errors.getvalue()

    def test_first_file_cannot_authorize_second_when_daily_disappears(self):
        result, calls, scans, records, errors = self.run_batch(
            lambda: (self.signatures / "daily.cld").unlink())
        self.assertEqual(result, 1)
        self.assertEqual(calls, [self.pdfs[0]])
        self.assertEqual(scans.call_count, 1)
        self.assertEqual(records.call_count, 1)
        self.assertIn("opening was stopped", errors)
        self.assertNotIn(str(self.root), errors)

    def test_freshness_expiry_mid_batch_blocks_second_scan(self):
        result, calls, scans, records, _ = self.run_batch(
            lambda: self.stamp.write_text(
                str(time.time() - scanner.MAX_DATABASE_AGE - 10)))
        self.assertEqual(result, 1)
        self.assertEqual(calls, [self.pdfs[0]])
        self.assertEqual(scans.call_count, 1)
        self.assertEqual(records.call_count, 1)

    def test_symlinked_success_stamp_cannot_authorize_scanning(self):
        outside = self.root / "forged-stamp"
        outside.write_text(str(time.time()))
        self.stamp.unlink()
        self.stamp.symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            scanner.check_database()
        result, calls, scans, records, _ = self.run_batch(lambda: None)
        self.assertEqual(result, 1)
        self.assertEqual(calls, [])
        self.assertEqual(scans.call_count, 0)
        self.assertEqual(records.call_count, 0)

    def test_symlinked_database_directory_cannot_authorize_scanning(self):
        other = self.root / "external"
        self.signatures.rename(other)
        self.signatures.symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            scanner.check_database()
        result, calls, scans, records, _ = self.run_batch(lambda: None)
        self.assertEqual(result, 1)
        self.assertEqual(calls, [])
        self.assertEqual(scans.call_count, 0)
        self.assertEqual(records.call_count, 0)

    def test_valid_database_allows_all_items_without_mutation(self):
        result, calls, scans, records, errors = self.run_batch(lambda: None)
        self.assertEqual(result, 0, errors)
        self.assertEqual(calls, self.pdfs)
        self.assertEqual(scans.call_count, 2)
        self.assertEqual(records.call_count, 2)
        self.assertTrue((self.signatures / "daily.cld").is_file())

    def test_existing_scanner_and_user_customizations_unchanged(self):
        source = (ROOT / "scan-and-open.py").read_text()
        self.assertIn("check_database()\n            record_scan_request(", source)
        self.assertIn("MAX_DATABASE_AGE = 48 * 60 * 60", source)
        self.assertIn("if not has_signature_file('daily') or not has_signature_file('main')", source)
        self.assertIn("remove_quarantine(path)", source)
        self.assertIn("verify_launch_target(path", source)
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("python3 scripts/run-test.py tests/general/mandatory-signature-gate.py -v", ci)


if __name__ == "__main__":
    unittest.main()
