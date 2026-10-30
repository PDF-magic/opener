#!/usr/bin/env python3
"""Keep the browser viewer guide discoverable and its comparisons complete."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/browser-pdf-viewers.md"


class BrowserViewerDocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cls.guide = GUIDE.read_text(encoding="utf-8")

    def test_readme_links_to_guide_in_target_section(self):
        start = self.readme.index("## PDF target application")
        link = self.readme.index("[Browser PDF viewer differences](docs/browser-pdf-viewers.md)")
        self.assertGreater(link, start)
        self.assertTrue(GUIDE.is_file())

    def test_comparison_has_one_row_for_each_browser(self):
        identifiers = {
            "com.brave.Browser", "com.google.Chrome", "org.chromium.Chromium",
            "com.microsoft.edgemac", "com.vivaldi.Vivaldi",
            "com.operasoftware.Opera", "company.thebrowser.Browser",
            "org.mozilla.firefox", "com.apple.Safari",
        }
        rows = re.findall(r"^\| (.+?) \| `([^`]+)` \| (.+?) \|$", self.guide, re.MULTILINE)
        self.assertEqual(len(rows), len(identifiers))
        self.assertEqual({row[1] for row in rows}, identifiers)

    def test_distinguishes_viewer_features_and_preferences(self):
        for token in ("Chromium-derived", "PDF.js", "Preview", "OCR",
                      "annotation", "download", "not identical"):
            with self.subTest(token=token):
                self.assertIn(token.lower(), self.guide.lower())

    def test_scan_and_identity_gates_are_explicit(self):
        for token in ("ClamAV", "file-integrity", "quarantine",
                      "local-file-availability", "verify-pdf-target.swift",
                      "launch-scanned-file.swift", "not fall back"):
            with self.subTest(token=token):
                self.assertIn(token, self.guide)

    def test_repo_links_resolve(self):
        for link in ("../README.md", "../verify-pdf-target.swift",
                     "../launch-scanned-file.swift"):
            self.assertTrue((GUIDE.parent / link).is_file(), link)

    def test_vendor_sources_are_linked(self):
        for host in ("support.google.com/chrome/", "support.mozilla.org/en-US/",
                     "github.com/mozilla/pdf.js", "support.apple.com/guide/preview/"):
            self.assertIn(host, self.guide)


if __name__ == "__main__":
    unittest.main()
