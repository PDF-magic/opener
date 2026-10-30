#!/usr/bin/env python3
"""opener-0336: immediate, explicit preview persistence without activating scanner tiers."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
VIEW = (ROOT / "PDFMagicOpenerApp/ProtectionSettingsView.swift").read_text(encoding="utf-8")
SHARED = (ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift").read_text(encoding="utf-8")
SCANNER = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
CI = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")


class ProtectionChoicePersistenceTests(unittest.TestCase):
    def test_card_saves_only_an_explicit_planned_choice(self):
        self.assertIn("PlannedProtectionLevelPreference.saveExplicitChoice(level)", VIEW)
        self.assertIn("PreferredProtectionLevel(rawValue: tier.rawValue)", VIEW)
        self.assertIn("selectedPreview = tier", VIEW)
        self.assertIn("previewSaveStatus", VIEW)
        self.assertIn("Could not save the preview choice", VIEW)
        self.assertIn("Active protection remains Built-in.", VIEW)

    def test_reopening_settings_restores_preview_not_active_policy(self):
        self.assertIn(".onAppear {", VIEW)
        self.assertIn("PlannedProtectionLevelPreference.selected()", VIEW)
        self.assertIn("PlannedProtectionTier(rawValue: stored.rawValue)", VIEW)
        self.assertIn('accessibilityIdentifier("protectionPreviewSaveStatus")', VIEW)
        self.assertIn('accessibilityIdentifier("activeBuiltInProtection")', VIEW)
        self.assertIn("Preview only · Not available as an active policy", VIEW)

    def test_persistence_is_separate_from_enforced_scanning(self):
        self.assertIn('static let key = "preferredProtectionLevel"', SHARED)
        self.assertIn("static func saveExplicitChoice(", SHARED)
        self.assertIn('static let key = "selectedProtectionProfile"', SHARED)
        self.assertIn("if not cached_clean(cache_id):", SCANNER)
        for forbidden in ("SelectedProtectionProfilePreference.save", "scan_and_open(",
                          "@AppStorage", "UserDefaults", "FileManager", "Process("):
            self.assertNotIn(forbidden, VIEW)
        self.assertIn("choosing a card does not enable it", VIEW)

    def test_real_restart_regression_is_required_in_macos_ci(self):
        self.assertIn("test-protection-choice-restart.swift", CI)
        self.assertIn("test-protection-choice-persistence.py -v", CI)
        self.assertIn("test-protection-choice-restart.swift", "\n".join(
            p.name for p in ROOT.glob("test-protection-choice-restart.swift")))


if __name__ == "__main__":
    unittest.main()
