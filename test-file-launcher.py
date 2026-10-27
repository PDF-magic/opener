#!/usr/bin/env python3
"""Verify launch selection is independent of ClamAV and stays fail-closed."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from file_launcher import PDF_DEFAULT_BUNDLE_ID, launch_clean_file


ROOT = Path(__file__).resolve().parent


class FileLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target_app = self.root / 'Brave Browser.app'
        self.target_app.mkdir()
        target = patch('file_launcher.resolve_target_application', return_value=str(self.target_app))
        target.start()
        self.addCleanup(target.stop)

    def test_pdf_uses_existing_brave_destination_even_with_uppercase_extension(self):
        pdf = self.root / "a document.PDF"
        pdf.write_bytes(b"%PDF-1.4\n")
        with patch("file_launcher.subprocess.run") as run:
            launch_clean_file(pdf)
        run.assert_called_once_with(
            ["/usr/bin/open", "-a", str(self.target_app), str(pdf)], check=True
        )
        self.assertEqual(PDF_DEFAULT_BUNDLE_ID, "com.brave.Browser")

    def test_non_pdf_uses_system_default_application(self):
        document = self.root / "file with spaces.txt"
        document.write_text("safe")
        with patch("file_launcher.subprocess.run") as run:
            launch_clean_file(document)
        run.assert_called_once_with(["/usr/bin/open", str(document)], check=True)

    def test_app_bundle_uses_default_open_behavior(self):
        bundle = self.root / "Example.app"
        bundle.mkdir()
        with patch("file_launcher.subprocess.run") as run:
            launch_clean_file(bundle)
        run.assert_called_once_with(["/usr/bin/open", str(bundle)], check=True)

    def test_missing_pdf_application_never_launches(self):
        with patch('file_launcher.resolve_target_application',
                   side_effect=RuntimeError('Target application unavailable')), \
                patch('file_launcher.subprocess.run') as run:
            with self.assertRaisesRegex(RuntimeError, 'Target application unavailable'):
                launch_clean_file(self.root / 'missing.pdf')
        run.assert_not_called()

    def test_open_failure_is_not_swallowed(self):
        document = self.root / "file.pdf"
        with patch("file_launcher.subprocess.run",
                   side_effect=subprocess.CalledProcessError(1, "/usr/bin/open")):
            with self.assertRaises(subprocess.CalledProcessError):
                launch_clean_file(document)

    def test_scanner_delegates_selection_without_brave_policy(self):
        source = (ROOT / "scan-and-open.py").read_text()
        self.assertNotIn("com.brave.Browser", source)
        self.assertNotIn("PDF_DEFAULT_BUNDLE_ID", source)
        self.assertIn("prepare_launch_command(path)", source)
        self.assertIn("launch_clean_file(path, prepared_command=command)", source)
        self.assertLess(source.index("command = prepare_launch_command(path)"),
                        source.index("remove_quarantine(path)\n    launch_clean_file"))

    def test_installer_deploys_launch_module_with_scanner(self):
        script = (ROOT / "install-allow-and-open.sh").read_text()
        line = next(line for line in script.splitlines()
                    if line.startswith('cp "$script_dir/allow-and-open.sh"'))
        self.assertIn('"$script_dir/scan-and-open.py"', line)
        self.assertIn('"$script_dir/file_launcher.py"', line)
        self.assertIn('"$install_dir/"', line)


if __name__ == "__main__":
    unittest.main()
