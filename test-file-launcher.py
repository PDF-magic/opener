#!/usr/bin/env python3
"""Verify launch selection is independent of ClamAV and stays fail-closed."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from file_launcher import NATIVE_LAUNCHER, PDF_DEFAULT_BUNDLE_ID, launch_clean_file


ROOT = Path(__file__).resolve().parent


class FileLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_pdf_uses_existing_brave_destination_even_with_uppercase_extension(self):
        pdf = self.root / "a document.PDF"
        pdf.write_bytes(b"%PDF-1.4\n")
        with patch("file_launcher.subprocess.run") as run:
            launch_clean_file(pdf)
        run.assert_called_once_with(
            [str(NATIVE_LAUNCHER), "--bundle-id", PDF_DEFAULT_BUNDLE_ID, str(pdf)], check=True
        )
        self.assertEqual(PDF_DEFAULT_BUNDLE_ID, "com.brave.Browser")

    def test_non_pdf_uses_system_default_application(self):
        document = self.root / "file with spaces.txt"
        document.write_text("safe")
        with patch("file_launcher.subprocess.run") as run:
            launch_clean_file(document)
        run.assert_called_once_with([str(NATIVE_LAUNCHER), str(document)], check=True)

    def test_app_bundle_uses_default_open_behavior(self):
        bundle = self.root / "Example.app"
        bundle.mkdir()
        with patch("file_launcher.subprocess.run") as run:
            launch_clean_file(bundle)
        run.assert_called_once_with([str(NATIVE_LAUNCHER), str(bundle)], check=True)

    def test_open_failure_is_not_swallowed(self):
        document = self.root / "file.pdf"
        with patch("file_launcher.subprocess.run",
                   side_effect=subprocess.CalledProcessError(1, str(NATIVE_LAUNCHER))):
            with self.assertRaises(subprocess.CalledProcessError):
                launch_clean_file(document)

    def test_scanner_delegates_selection_without_brave_policy(self):
        source = (ROOT / "scan-and-open.py").read_text()
        self.assertNotIn("com.brave.Browser", source)
        self.assertNotIn("PDF_DEFAULT_BUNDLE_ID", source)
        self.assertIn("launch_clean_file(path)", source)
        self.assertLess(source.index("remove_quarantine(path)\n    # The scan engine"),
                        source.index("launch_clean_file(path)"))

    def test_native_workspace_api_routing(self):
        swift = (ROOT / "launch-scanned-file.swift").read_text()
        self.assertIn("NSWorkspace", swift)
        self.assertIn("workspace.open([target], withApplicationAt:", swift)
        self.assertIn("workspace.openApplication(at: target", swift)
        self.assertIn("workspace.open(target)", swift)

    def test_installer_deploys_launch_module_with_scanner(self):
        script = (ROOT / "install-allow-and-open.sh").read_text()
        line = next(line for line in script.splitlines()
                    if line.startswith('cp "$script_dir/allow-and-open.sh"'))
        self.assertIn('"$script_dir/scan-and-open.py"', line)
        self.assertIn('"$script_dir/file_launcher.py"', line)
        self.assertIn('"$install_dir/"', line)
        self.assertIn('swiftc -O "$script_dir/launch-scanned-file.swift"', script)
        self.assertIn('"$install_dir/launch-scanned-file"', script)


if __name__ == "__main__":
    unittest.main()
