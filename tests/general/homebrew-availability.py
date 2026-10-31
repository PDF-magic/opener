#!/usr/bin/env python3
"""Hermetic Homebrew availability detection and installer preflight tests."""

import contextlib
import importlib.util
from io import StringIO
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("detect_homebrew", ROOT / "scripts/detect_homebrew.py")
detector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(detector)


class HomebrewDetectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.arm = self.root / "arm" / "brew"
        self.intel = self.root / "intel" / "brew"

    def executable(self, path, mode=0o755):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(mode)
        return path

    def detect(self, known_paths=None, path=""):
        if known_paths is None:
            known_paths = (self.arm, self.intel)
        return detector.detect_homebrew(known_paths=known_paths, search_path=path)

    def test_missing_homebrew_reports_unavailable_without_installing(self):
        self.assertIsNone(self.detect())
        with patch.object(detector, "detect_homebrew", return_value=None):
            stdout, stderr = StringIO(), StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(detector.main(), 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("Homebrew is unavailable", stderr.getvalue())

    def test_detects_apple_silicon_and_intel_prefixes_in_order(self):
        self.executable(self.intel)
        self.assertEqual(self.detect(), str(self.intel))
        self.executable(self.arm)
        self.assertEqual(self.detect(), str(self.arm))
        with patch.object(detector, "detect_homebrew", return_value=str(self.arm)):
            stdout = StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(detector.main(), 0)
            self.assertEqual(stdout.getvalue(), str(self.arm) + "\n")

    def test_detects_custom_absolute_path_even_with_sanitized_finder_path(self):
        custom = self.executable(self.root / "custom" / "bin" / "brew")
        self.assertEqual(self.detect(known_paths=(), path=str(custom.parent)), str(custom))
        self.assertIsNone(self.detect(known_paths=(), path="/nonexistent"))

    def test_rejects_relative_and_empty_path_entries(self):
        candidate = self.executable(self.root / "relative" / "brew")
        with patch.dict(os.environ, {"PATH": "relative::"}):
            self.assertIsNone(self.detect(known_paths=(), path="relative::"))
        self.assertTrue(candidate.exists())

    def test_rejects_directories_non_executables_and_broken_links(self):
        self.arm.mkdir(parents=True)
        self.executable(self.intel, mode=0o644)
        self.assertIsNone(self.detect())
        self.intel.unlink()
        self.intel.symlink_to(self.root / "missing")
        self.assertIsNone(self.detect())

    def test_homebrew_symlink_is_recognized_without_running_binary(self):
        target = self.executable(self.root / "Cellar" / "brew")
        self.arm.parent.mkdir(parents=True)
        self.arm.symlink_to(target)
        before = (target.read_bytes(), target.stat().st_mtime_ns)
        self.assertEqual(self.detect(), str(self.arm))
        self.assertEqual((target.read_bytes(), target.stat().st_mtime_ns), before)

    def test_installer_checks_availability_only_when_scanner_missing(self):
        source = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
        self.assertIn('brew_executable="$(python3 "$script_dir/scripts/detect_homebrew.py")"', source)
        self.assertIn('"$brew_executable" install clamav', source)
        self.assertNotIn("\n    brew install clamav\n", source)
        preflight = source.index('if ! [ -x /opt/homebrew/bin/clamscan ]')
        detector = source.index('scripts/detect_homebrew.py')
        installation = source.index('"$brew_executable" install clamav')
        mutation = source.index('mkdir -p "$install_dir/signatures"')
        self.assertLess(preflight, detector)
        self.assertLess(detector, installation)
        self.assertLess(installation, mutation)
        self.assertIn('if ! brew_executable=', source[preflight:installation])
        self.assertIn('exit 1', source[detector:installation])


if __name__ == "__main__":
    unittest.main()
