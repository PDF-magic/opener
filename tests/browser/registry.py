#!/usr/bin/env python3
"""Keep supported browser IDs, deployment, and the viewer guide in sync."""

from pathlib import Path
import re
import unittest

import browser_registry as registry
import file_launcher as launcher

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_BROWSERS = {
    "brave": "com.brave.Browser",
    "chrome": "com.google.Chrome",
    "chromium": "org.chromium.Chromium",
    "edge": "com.microsoft.edgemac",
    "vivaldi": "com.vivaldi.Vivaldi",
    "opera": "com.operasoftware.Opera",
    "arc": "company.thebrowser.Browser",
    "firefox": "org.mozilla.firefox",
    "safari": "com.apple.Safari",
}


class BrowserRegistryTests(unittest.TestCase):
    def test_identifiers_are_complete_unique_and_stable(self):
        self.assertEqual(dict(registry.SUPPORTED_BROWSERS), EXPECTED_BROWSERS)
        self.assertEqual(registry.SUPPORTED_BROWSER_BUNDLE_IDS,
                         frozenset(EXPECTED_BROWSERS.values()))
        self.assertEqual(len(registry.SUPPORTED_BROWSER_BUNDLE_IDS),
                         len(EXPECTED_BROWSERS))
        with self.assertRaises(TypeError):
            registry.SUPPORTED_BROWSERS["brave"] = "com.example.Impostor"

    def test_default_matches_launcher_without_changing_custom_targets(self):
        self.assertEqual(registry.DEFAULT_BROWSER_BUNDLE_ID, "com.brave.Browser")
        self.assertEqual(launcher.PDF_DEFAULT_BUNDLE_ID,
                         registry.DEFAULT_BROWSER_BUNDLE_ID)
        self.assertTrue(launcher._valid_bundle_identifier("com.example.CustomViewer"))
        self.assertTrue(launcher._valid_bundle_identifier("com.apple.Preview"))
        self.assertFalse(launcher._valid_bundle_identifier(
            launcher.PDF_OPENER_BUNDLE_ID))

    def test_browser_viewer_guide_lists_exact_registered_identifiers(self):
        guide = (ROOT / "docs/browser-pdf-viewers.md").read_text(encoding="utf-8")
        rows = re.findall(r"^\| (.+?) \| `([^`]+)` \| (.+?) \|$",
                          guide, re.MULTILINE)
        self.assertEqual(len(rows), len(EXPECTED_BROWSERS))
        self.assertEqual({bundle_id for _, bundle_id, _ in rows},
                         registry.SUPPORTED_BROWSER_BUNDLE_IDS)
        self.assertIn("../browser_registry.py", guide)

    def test_native_primary_list_matches_supported_registry(self):
        source = (ROOT / "browser-preference-list.swift").read_text(encoding="utf-8")
        match = re.search(
            r"private let supportedBrowserBundleIDs: Set<String> = \[([^\]]+)\]",
            source,
        )
        self.assertIsNotNone(match, "Native primary list must declare known IDs")
        identifiers = re.findall(r'"([^"]+)"', match.group(1))
        self.assertEqual(set(identifiers), registry.SUPPORTED_BROWSER_BUNDLE_IDS)
        self.assertEqual(len(identifiers), len(registry.SUPPORTED_BROWSER_BUNDLE_IDS))

    def test_registry_is_deployed_with_launcher(self):
        installer = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
        line = next(line for line in installer.splitlines()
                    if line.startswith('cp "$script_dir/allow-and-open.sh"'))
        self.assertIn('"$script_dir/file_launcher.py"', line)
        self.assertIn('"$script_dir/browser_registry.py"', line)


if __name__ == "__main__":
    unittest.main()
