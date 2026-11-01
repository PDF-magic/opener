#!/usr/bin/env python3
"""Keep the browser-selection user guide aligned with the verified preferences UI."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
GUIDE = (ROOT / "docs/select-browser.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
INDEX = (ROOT / "docs/README.md").read_text(encoding="utf-8")
GENERAL = (ROOT / "PDFMagicOpenerApp/GeneralSettingsView.swift").read_text(encoding="utf-8")
PREFS = (ROOT / "PDFMagicOpenerApp/DefaultPDFBrowserPreferences.swift").read_text(encoding="utf-8")
CHOOSER = (ROOT / "select-custom-pdf-application.py").read_text(encoding="utf-8")
CI = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")


class BrowserSelectionGuideTests(unittest.TestCase):
    def test_guide_is_discoverable_and_has_actual_selection_steps(self):
        self.assertIn("(docs/select-browser.md)", README)
        self.assertIn("(select-browser.md)", INDEX)
        for item in ("General", "Default PDF browser", "Browser for scanned PDFs",
                     "Default PDF browser saved.", "Command-comma", "⌘,",
                     "Existing selection (not in installed"):
            with self.subTest(item=item):
                self.assertIn(item, GUIDE)

    def test_settings_steps_match_real_picker_and_verified_save(self):
        for item in ('GroupBox("Default PDF browser")',
                     'Picker("Browser for scanned PDFs"',
                     "DefaultPDFBrowserPreferences.saveVerified(option)",
                     "Default PDF browser saved.",
                     "Could not verify or save that browser"):
            with self.subTest(item=item):
                self.assertIn(item, GENERAL)
        for item in ('"target-app.txt"', '"select-custom-pdf-application.py"',
                     '"--application"', "option.applicationURL.path",
                     "return process.terminationReason == .exit"):
            with self.subTest(item=item):
                self.assertIn(item, PREFS)
        self.assertIn("previous choice", GUIDE)

    def test_custom_app_instructions_use_installed_verifier(self):
        for item in ("select-custom-pdf-application.py", "--application",
                     "/Applications/Custom Browser.app", "Launch Services",
                     "read-only", "system-default-browser"):
            with self.subTest(item=item):
                self.assertIn(item, GUIDE)
        self.assertIn('parser.add_argument("--application"', CHOOSER)
        self.assertIn("verified.returncode != 0", CHOOSER)
        self.assertIn("persist_preference(identifier, destination)", CHOOSER)
        self.assertIn("os.O_NOFOLLOW", CHOOSER)

    def test_guide_preserves_scanner_and_user_preference_boundaries(self):
        for item in ("ClamAV", "quarantine", "signature-freshness",
                     "file-integrity", "blocks opening", "silent fallback",
                     "previous choice", "default web browser",
                     "default PDF file handler", "Open With → PDF Magic Opener"):
            with self.subTest(item=item):
                self.assertIn(item, GUIDE)
        self.assertIn("browser-selection-docs.py -v", CI)


if __name__ == "__main__":
    unittest.main()
