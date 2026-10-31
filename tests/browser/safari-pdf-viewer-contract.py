#!/usr/bin/env python3
"""Guard that Safari PDF verification uses a real browser and isolated files."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests/browser/safari-pdf-viewer.py"
CI = ROOT / ".github/workflows/ci.yml"
DOC = ROOT / "docs/browser-pdf-viewers.md"
BACKGROUND = ROOT / "extensions/webextension/src/background.js"
SAFARI_MANIFEST = ROOT / "extensions/safari/manifest.json"
SHARED_MANIFEST = ROOT / "extensions/webextension/manifest.json"


class SafariViewerContractTests(unittest.TestCase):
    def test_live_safari_automation_is_mandatory(self):
        harness = HARNESS.read_text(encoding="utf-8")
        ci = CI.read_text(encoding="utf-8")
        self.assertIn('name: Real Safari PDF viewer behavior', ci)
        self.assertIn("runs-on: macos-latest", ci)
        self.assertIn("sudo /usr/bin/safaridriver --enable", ci)
        self.assertIn("python3 tests/browser/safari-pdf-viewer.py --live", ci)
        self.assertIn('browserName": "safari"', harness)
        self.assertIn('"/usr/bin/safaridriver"', harness)
        self.assertIn('"/session"', harness)
        self.assertIn('"/url"', harness)
        self.assertIn('"/screenshot"', harness)
        self.assertIn('sample_png_color(shot, color)', harness)
        self.assertIn('observed_fraction >= 0.035', harness)
        self.assertIn('counts.get(route, 0) >= 1', harness)
        self.assertIn('current == url', harness)
        self.assertIn("raise AssertionError(", harness)
        self.assertNotIn("pytest.skip", harness)
        self.assertNotIn("unittest.skip", harness)
        self.assertNotIn("return 0", harness)
        self.assertIn('python3 tests/browser/safari-pdf-viewer.py --self-test', ci)

    def test_fixtures_are_inline_local_and_no_user_state_mutates(self):
        harness = HARNESS.read_text(encoding="utf-8")
        self.assertIn('"127.0.0.1"', harness)
        self.assertIn('"/safari-viewer.pdf"', harness)
        self.assertIn('"/pdf-by-mime"', harness)
        self.assertIn('"Content-Type", "application/pdf"', harness)
        self.assertIn('"Content-Disposition", "inline"', harness)
        self.assertIn('PDF Magic Safari Viewer Test', harness)
        self.assertIn("server.shutdown()", harness)
        self.assertIn('webdriver("DELETE"', harness)
        for forbidden in (
            "https://", "file://", "downloads.open", "scan-and-open",
            "sendNativeMessage", "connectNative", "defaults write",
            "killall Safari", "rm -rf", "open -a Safari", "requests.get",
            "http://example", "launch-scanned-file"
        ):
            self.assertNotIn(forbidden, harness)
        self.assertFalse(re.search(r"(?m)^\\s*except Exception:\\s*pass", harness))
        self.assertIn("Safari", DOC.read_text(encoding="utf-8"))
        self.assertTrue(BACKGROUND.read_text(encoding="utf-8").strip().endswith("void 0;"))
        self.assertIn('"host_permissions": []', SHARED_MANIFEST.read_text(encoding="utf-8"))
        self.assertIn('"host_permissions": []', SAFARI_MANIFEST.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
