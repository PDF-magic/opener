#!/usr/bin/env python3
"""Document and lock the existing ClamAV distribution choice (opener-0957)."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "install-allow-and-open.sh"
SCANNER = ROOT / "scan-and-open.py"
DECISION = ROOT / "docs/clamav-homebrew-decision.md"
README = ROOT / "README.md"

TRUSTED_SCANNERS = (
    "/opt/homebrew/bin/clamscan",
    "/usr/local/bin/clamscan",
    "/usr/local/clamav/bin/clamscan",
)


class HomebrewDependencyDecisionTests(unittest.TestCase):
    def test_homebrew_provisions_only_after_existing_scanner_checks(self):
        source = INSTALLER.read_text(encoding="utf-8")
        check = "if ! [ -x /opt/homebrew/bin/clamscan ]"
        self.assertIn(check, source)
        start = source.index(check)
        end = source.index("\nfi", start)
        fallback = source[start:end]
        for candidate in TRUSTED_SCANNERS:
            with self.subTest(candidate=candidate):
                self.assertIn(f"[ -x {candidate} ]", fallback)
        self.assertIn("brew install clamav", fallback)
        self.assertEqual(source.count("brew install clamav"), 1)
        self.assertNotIn("brew install clamav", source[:start])

    def test_non_homebrew_installs_use_the_same_fail_closed_scan_gate(self):
        runtime = SCANNER.read_text(encoding="utf-8")
        candidates = runtime.split("CLAMAV_CANDIDATES = (", 1)[1].split(")", 1)[0]
        for candidate in TRUSTED_SCANNERS:
            with self.subTest(candidate=candidate):
                self.assertIn(repr(candidate), candidates)
        self.assertIn("scanner = detect_clamav_installation()", runtime)
        self.assertIn("require_supported_scanner_version(scanner)", runtime)
        self.assertIn("raise RuntimeError('ClamAV is unavailable.", runtime)

    def test_decision_is_visible_and_does_not_change_installed_engines(self):
        guide = DECISION.read_text(encoding="utf-8")
        readme = README.read_text(encoding="utf-8")
        self.assertIn("Retain Homebrew as the default provisioning route", guide)
        self.assertIn("not a required", guide)
        self.assertIn("docs/clamav-homebrew-decision.md", readme)
        installer = INSTALLER.read_text(encoding="utf-8")
        for forbidden in ("brew upgrade clamav", "brew uninstall clamav",
                          "brew services start clamav"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, installer)


if __name__ == "__main__":
    unittest.main()
