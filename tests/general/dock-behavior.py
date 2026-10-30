#!/usr/bin/env python3
"""Check explicit Dock policy for preferences and the independent PDF scan helper."""
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"
ENTRY = ROOT / "PDFMagicOpenerApp" / "PDFMagicOpenerApp.swift"
SCANNER = ROOT / "brave-pdf-opener.swift"
INSTALLER = ROOT / "install-allow-and-open.sh"


def target_build_settings(project, config_id):
    """Inspect the exact Xcode native-app target configuration, not global defaults."""
    match = re.search(
        re.escape(config_id) +
        r"\s*=\s*\{\s*isa\s*=\s*XCBuildConfiguration;\s*"
        r"buildSettings\s*=\s*\{(?P<settings>.*?)\n\s*\};",
        project, re.DOTALL)
    if match is None:
        raise AssertionError(f"Missing native-app build configuration {config_id}")
    return match.group("settings")


class DockBehaviorTests(unittest.TestCase):
    def test_regular_preferences_app_has_explicit_dock_policy_in_both_builds(self):
        project = PROJECT.read_text(encoding="utf-8")
        for configuration, identifier in (
            ("Debug", "A1000000000000000000000E"),
            ("Release", "A1000000000000000000000F"),
        ):
            with self.subTest(configuration=configuration):
                settings = target_build_settings(project, identifier)
                self.assertIn("INFOPLIST_KEY_LSUIElement = NO;", settings)
                self.assertIn("GENERATE_INFOPLIST_FILE = YES;", settings)
                self.assertIn(
                    "PRODUCT_BUNDLE_IDENTIFIER = local.studio.pdfmagicopener.swiftui;",
                    settings)
                self.assertNotIn("INFOPLIST_KEY_LSBackgroundOnly = YES;", settings)
        self.assertEqual(project.count("INFOPLIST_KEY_LSUIElement = NO;"), 2)
        self.assertNotIn("CFBundleDocumentTypes", project)

    def test_preferences_keep_a_normal_window_and_activation_behavior(self):
        app = ENTRY.read_text(encoding="utf-8")
        self.assertIn("struct PDFMagicOpenerApp: App", app)
        self.assertIn("WindowGroup", app)
        self.assertNotIn("setActivationPolicy(.accessory)", app)
        self.assertNotIn("setActivationPolicy(.prohibited)", app)
        self.assertNotIn("DocumentGroup", app)

    def test_existing_pdf_handler_stays_an_accessory_not_a_second_dock_app(self):
        scanner = SCANNER.read_text(encoding="utf-8")
        self.assertIn("app.setActivationPolicy(.accessory)", scanner)
        install = INSTALLER.read_text(encoding="utf-8")
        marker = "python3 - \"$app\" \"$install_dir\" \"$app_name\" <<'CONFIG'\n"
        self.assertEqual(install.count(marker), 1)
        config = install.split(marker, 1)[1].split("\nCONFIG\n", 1)[0]
        with tempfile.TemporaryDirectory(prefix="opener-dock-policy-") as temp:
            home = Path(temp)
            app = home / "Applications" / "PDF Magic Opener.app"
            (app / "Contents").mkdir(parents=True)
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            result = subprocess.run(
                [sys.executable, "-", str(app), str(home / "runtime"),
                 "PDF Magic Opener"], input=config, text=True,
                capture_output=True, env={**os.environ, "HOME": str(home)},
                check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            with (app / "Contents" / "Info.plist").open("rb") as stream:
                info = plistlib.load(stream)
            self.assertIs(info.get("LSUIElement"), True)
            self.assertNotIn("LSBackgroundOnly", info)
            self.assertEqual(info["CFBundleExecutable"], "PDFOpener")
            self.assertEqual(info["CFBundleIdentifier"], "local.studio.brave-pdf-opener")
            self.assertEqual(
                info["CFBundleDocumentTypes"][0]["LSItemContentTypes"],
                ["com.adobe.pdf"])


if __name__ == "__main__":
    unittest.main()
