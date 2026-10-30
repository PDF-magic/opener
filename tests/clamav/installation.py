#!/usr/bin/env python3
"""Read-only ClamAV installation discovery regressions (opener-0354)."""

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "clamav_installation_gate", ROOT / "scan-and-open.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ClamAVInstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.candidates = (
            root / "homebrew-arm" / "clamscan",
            root / "homebrew-intel" / "clamscan",
            root / "local-clamav" / "clamscan",
        )
        candidate_patch = patch.object(
            gate, "CLAMAV_CANDIDATES",
            tuple(str(candidate) for candidate in self.candidates),
        )
        candidate_patch.start()
        self.addCleanup(candidate_patch.stop)

    def make_binary(self, candidate, executable=True):
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        candidate.chmod(0o755 if executable else 0o644)

    def test_missing_scanner_is_reported_absent_and_fails_closed(self):
        self.assertIsNone(gate.detect_clamav_installation())
        with self.assertRaisesRegex(RuntimeError, "^ClamAV is unavailable"):
            gate.scanner_path()

    def test_detects_supported_paths_in_existing_priority_order(self):
        for candidate in reversed(self.candidates):
            self.make_binary(candidate)
        self.assertEqual(
            gate.detect_clamav_installation(), str(self.candidates[0])
        )
        # This test covers binary discovery, not the compatibility policy.
        with patch.object(gate, "require_supported_scanner_version", return_value="1.4.2"):
            self.assertEqual(gate.scanner_path(), str(self.candidates[0]))
        self.candidates[0].unlink()
        self.assertEqual(
            gate.detect_clamav_installation(), str(self.candidates[1])
        )

    def test_non_executable_file_is_not_an_installation(self):
        self.make_binary(self.candidates[0], executable=False)
        self.assertIsNone(gate.detect_clamav_installation())
        self.make_binary(self.candidates[1])
        self.assertEqual(
            gate.detect_clamav_installation(), str(self.candidates[1])
        )

    def test_executable_directory_is_not_an_installation(self):
        self.candidates[0].mkdir(parents=True)
        self.candidates[0].chmod(0o755)
        self.assertIsNone(gate.detect_clamav_installation())
        self.make_binary(self.candidates[1])
        self.assertEqual(
            gate.detect_clamav_installation(), str(self.candidates[1])
        )

    def test_homebrew_style_symlink_to_executable_is_supported(self):
        target = Path(self.temp.name) / "Cellar" / "clamav" / "bin" / "clamscan"
        self.make_binary(target)
        self.candidates[0].parent.mkdir(parents=True)
        self.candidates[0].symlink_to(target)
        self.assertEqual(gate.detect_clamav_installation(), str(self.candidates[0]))
        target.unlink()
        self.assertIsNone(gate.detect_clamav_installation())

    def test_untrusted_path_entries_are_not_treated_as_installed(self):
        unlisted = Path(self.temp.name) / "other-bin" / "clamscan"
        self.make_binary(unlisted)
        with patch.dict(os.environ, {"PATH": str(unlisted.parent)}):
            self.assertIsNone(gate.detect_clamav_installation())

    def test_detection_is_read_only_and_does_not_start_scanning(self):
        self.make_binary(self.candidates[0])
        with patch.object(gate.subprocess, "run") as run, \
                patch.object(gate.subprocess, "check_output") as version, \
                patch.object(gate, "check_database") as signatures, \
                patch.object(gate, "scan_and_open") as scan, \
                patch.object(gate, "remove_quarantine") as quarantine:
            self.assertEqual(
                gate.detect_clamav_installation(), str(self.candidates[0])
            )
            run.assert_not_called()
            version.assert_not_called()
            signatures.assert_not_called()
            scan.assert_not_called()
            quarantine.assert_not_called()


if __name__ == "__main__":
    unittest.main()
