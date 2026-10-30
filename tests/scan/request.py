#!/usr/bin/env python3
"""Verify application attribution for each scan and both scanner entry points."""
import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("scan_and_open", ROOT / "scan-and-open.py")
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)


class ScanRequestApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "scan-requests.sqlite3"
        db_patch = patch.object(opener, "SCAN_REQUEST_DB", self.db)
        db_patch.start()
        self.addCleanup(db_patch.stop)

    def run_request(self, paths, application=None, scan_error=None):
        environment = os.environ.copy()
        environment.pop(opener.REQUESTING_APPLICATION_ENV, None)
        if application is not None:
            environment[opener.REQUESTING_APPLICATION_ENV] = application
        with patch.dict(os.environ, environment, clear=True), \
                patch.object(opener, "validate_scan_request", return_value=Path("/example/one.pdf")), \
                patch.object(opener, "scanner_path", return_value="/scanner"), \
                patch.object(opener, "check_database"), \
                patch.object(opener, "scan_and_open", side_effect=scan_error) as scan, \
                patch("sys.stderr"):
            result = opener.main(paths)
        return result, scan

    def records(self):
        with sqlite3.connect(str(self.db)) as connection:
            rows = connection.execute(
                "SELECT requesting_application FROM scan_request_applications ORDER BY id"
            ).fetchall()
            columns = [entry[1] for entry in connection.execute(
                "PRAGMA table_info(scan_request_applications)"
            ).fetchall()]
        return [row[0] for row in rows], columns

    def test_one_record_per_attempt_with_private_metadata_only(self):
        status, scan = self.run_request(["/example/one.pdf", "/example/two.pdf"],
                                        application="PDF Magic Opener")
        self.assertEqual(status, 0)
        self.assertEqual(scan.call_count, 2)
        names, columns = self.records()
        self.assertEqual(names, ["PDF Magic Opener", "PDF Magic Opener"])
        self.assertEqual(columns, ["id", "requested_at", "requesting_application"])
        self.assertEqual(self.db.stat().st_mode & 0o777, 0o600)

    def test_direct_python_entry_point_defaults_to_command_line(self):
        status, _ = self.run_request(["/example/one.pdf"])
        self.assertEqual(status, 0)
        self.assertEqual(self.records()[0], ["Command Line"])

    def test_failed_scan_still_records_requester(self):
        status, _ = self.run_request(["/example/one.pdf"], application="Allow and Open",
                                      scan_error=RuntimeError("scan refused"))
        self.assertEqual(status, 1)
        self.assertEqual(self.records()[0], ["Allow and Open"])

    def test_unavailable_log_blocks_scan(self):
        with patch.object(opener, "validate_scan_request", return_value=Path("/example/one.pdf")), \
                patch.object(opener, "scanner_path", return_value="/scanner"), \
                patch.object(opener, "check_database"), \
                patch.object(opener, "record_scan_request",
                             side_effect=sqlite3.OperationalError("read only")), \
                patch.object(opener, "scan_and_open") as scan, \
                patch("sys.stderr"):
            self.assertEqual(opener.main(["/example/one.pdf"]), 1)
        scan.assert_not_called()

    def test_symlinked_database_refused(self):
        target = Path(self.temp.name) / "other.txt"
        target.write_text("preserve me")
        self.db.symlink_to(target)
        with self.assertRaisesRegex(RuntimeError, "symbolic link"):
            opener.record_scan_request("PDF Magic Opener")
        self.assertEqual(target.read_text(), "preserve me")

    def test_gate_passes_native_and_finder_origin_without_losing_paths(self):
        original = (ROOT / "allow-and-open.sh").read_text()
        original_call = 'exec /usr/bin/python3 "$script_dir/scan-and-open.py" "$@"'
        self.assertEqual(original.count(original_call), 1)
        temporary = Path(self.temp.name)
        gate = temporary / "allow-and-open.sh"
        gate.write_text(original.replace(original_call,
                          'exec /bin/bash "$script_dir/capture.sh" "$@"'))
        (temporary / "capture.sh").write_text(
            '#!/bin/bash\nprintf "%s\\n" "$PDF_MAGIC_REQUESTING_APPLICATION" "$@"\n'
        )
        for environment, expected_app in [
            ({"PDF_MAGIC_REQUESTING_APPLICATION": "PDF Magic Opener"}, "PDF Magic Opener"),
            ({}, "Allow and Open"),
        ]:
            with self.subTest(expected_app=expected_app):
                variables = os.environ.copy()
                variables.pop("PDF_MAGIC_REQUESTING_APPLICATION", None)
                variables.update(environment)
                result = subprocess.run(["/bin/bash", str(gate), "/document with spaces.pdf"],
                                        env=variables, capture_output=True, text=True, check=True)
                self.assertEqual(result.stdout.splitlines(),
                                 [expected_app, "/document with spaces.pdf"])
        native = (ROOT / "brave-pdf-opener.swift").read_text()
        self.assertIn('process.arguments = [script.path, path]', native)
        self.assertIn('environment["PDF_MAGIC_REQUESTING_APPLICATION"] = "PDF Magic Opener"', native)


if __name__ == "__main__":
    unittest.main()
