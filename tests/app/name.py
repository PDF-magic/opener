#!/usr/bin/env python3
"""Verify the application display name, generated plist, and safe legacy migration."""
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = (ROOT / "install-allow-and-open.sh").read_text()
APP_NAME = "PDF Magic Opener"
BUNDLE_ID = "local.studio.brave-pdf-opener"


def embedded_script(marker, terminator):
    assert INSTALLER.count(marker) == 1, f"Cannot find unique embedded {terminator} script"
    return INSTALLER.split(marker, 1)[1].split("\n" + terminator + "\n", 1)[0]


MIGRATION = embedded_script('python3 - "$legacy_app" "$app" <<\'MIGRATE\'\n', "MIGRATE")
PLIST_SCRIPT = embedded_script('python3 - "$app" "$install_dir" "$app_name" <<\'CONFIG\'\n', "CONFIG")


def write_app(path, identifier=BUNDLE_ID):
    (path / "Contents").mkdir(parents=True)
    with (path / "Contents/Info.plist").open("wb") as stream:
        plistlib.dump({"CFBundleIdentifier": identifier}, stream)


def invoke(script, *args, home=None):
    env = os.environ.copy()
    if home:
        env["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, "-", *(str(argument) for argument in args)],
        input=script, text=True, capture_output=True, env=env,
    )


class ApplicationNameTests(unittest.TestCase):
    def test_installer_names_application_and_preserves_identity(self):
        self.assertIn('app_name="PDF Magic Opener"', INSTALLER)
        self.assertIn('app="$HOME/Applications/$app_name.app"', INSTALLER)
        self.assertIn("local.studio.brave-pdf-opener", INSTALLER)
        self.assertIn("# PDF Magic Opener", (ROOT / "README.md").read_text())
        self.assertIn("PDF Magic Opener — Scanning", (ROOT / "scan-progress-view.swift").read_text())
        self.assertIn("ScanProgressPanel(", (ROOT / "brave-pdf-opener.swift").read_text())

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            app = home / "Applications" / (APP_NAME + ".app")
            (app / "Contents").mkdir(parents=True)
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            result = invoke(PLIST_SCRIPT, app, home / "runtime", APP_NAME, home=home)
            self.assertEqual(result.returncode, 0, result.stderr)
            with (app / "Contents" / "Info.plist").open("rb") as stream:
                info = plistlib.load(stream)
            self.assertEqual(info["CFBundleName"], APP_NAME)
            self.assertEqual(info["CFBundleDisplayName"], APP_NAME)
            self.assertEqual(info["CFBundleIdentifier"], BUNDLE_ID)
            self.assertEqual(info["CFBundleExecutable"], "PDFOpener")
            self.assertTrue(info["LSUIElement"])
            self.assertEqual(info["CFBundleDocumentTypes"][0]["LSItemContentTypes"], ["com.adobe.pdf"])

    def test_legacy_bundle_is_moved_without_changing_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            legacy = home / "Applications" / "Open PDFs in Brave.app"
            renamed = home / "Applications" / (APP_NAME + ".app")
            write_app(legacy)
            result = invoke(MIGRATION, legacy, renamed)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(legacy.exists())
            with (renamed / "Contents" / "Info.plist").open("rb") as stream:
                self.assertEqual(plistlib.load(stream)["CFBundleIdentifier"], BUNDLE_ID)
            self.assertEqual(invoke(MIGRATION, legacy, renamed).returncode, 0)

    def test_foreign_legacy_bundle_is_never_moved(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            legacy = home / "Applications" / "Open PDFs in Brave.app"
            renamed = home / "Applications" / (APP_NAME + ".app")
            write_app(legacy, "com.example.unrelated")
            result = invoke(MIGRATION, legacy, renamed)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(legacy.exists())
            self.assertFalse(renamed.exists())

    def test_legacy_collision_does_not_overwrite_either_app(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            legacy = home / "Applications" / "Open PDFs in Brave.app"
            renamed = home / "Applications" / (APP_NAME + ".app")
            write_app(legacy)
            write_app(renamed)
            result = invoke(MIGRATION, legacy, renamed)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(legacy.exists())
            self.assertTrue(renamed.exists())

    def test_foreign_new_bundle_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            renamed = Path(directory) / "Applications" / (APP_NAME + ".app")
            write_app(renamed, "com.example.unrelated")
            result = invoke(MIGRATION, renamed.with_name("Open PDFs in Brave.app"), renamed)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(renamed.exists())


if __name__ == "__main__":
    unittest.main()
