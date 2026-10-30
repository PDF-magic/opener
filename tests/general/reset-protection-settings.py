#!/usr/bin/env python3
"""opener-0340: Reset Protection Settings changes only an explicit preview."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
VIEW = (ROOT / "PDFMagicOpenerApp/ProtectionSettingsView.swift").read_text()
PREF = (ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift").read_text()
CI = (ROOT / ".github/workflows/ci.yml").read_text()
SCANNER = (ROOT / "scan-and-open.py").read_text()


class ResetProtectionSettingsTests(unittest.TestCase):
    def test_visible_accessible_confirmation_requires_explicit_action(self):
        for phrase in (
            'Button("Reset Protection Settings")',
            'accessibilityIdentifier("resetProtectionSettingsButton")',
            'accessibilityIdentifier("resetProtectionSettingsSection")',
            'showProtectionResetConfirmation = true',
            '.confirmationDialog(',
            'isPresented: $showProtectionResetConfirmation',
            'Button("Reset Protection Settings", role: .destructive)',
            'Button("Cancel", role: .cancel)',
            'resetProtectionPreview()',
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, VIEW)
        self.assertIn('ProtectionSettingsReset.reset()', VIEW)
        self.assertIn("Could not reset the protection preview", VIEW)
        self.assertIn("preview reset to Standard", VIEW)

    def test_reset_is_only_metadata_not_scanner_policy(self):
        portion = PREF.split("enum ProtectionSettingsReset {", 1)[1].split(
            "// A read-only effective view", 1
        )[0]
        self.assertIn("PlannedProtectionLevelPreference.key", portion)
        self.assertIn("PreferredProtectionLevel.standard.rawValue", portion)
        self.assertIn("SelectedProtectionProfilePreference.selected", portion)
        self.assertIn("ActiveConfigurationSchemaVersion.read", portion)
        self.assertIn("newInstallationMarker", portion)
        self.assertIn("PreferredProtectionLevel(rawValue: original) != nil", portion)
        self.assertIn("defaults.set(original,", portion)
        for forbidden in (
            "SelectedProtectionProfilePreference.save(",
            "ScanProgressPreference.key",
            "SuccessfulScanNotificationPreference.key",
            "BlockedFileNotificationPreference.key",
            "pdfBrowser",
            "removePersistentDomain", "removeObject",
            "scan-and-open",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, portion)
        self.assertNotIn("ProtectionSettingsReset", SCANNER)

    def test_ui_preserves_preview_selection_and_does_not_open_pdf(self):
        self.assertIn("PlannedProtectionLevelPreference.saveExplicitChoice(level)", VIEW)
        self.assertIn("PlannedProtectionLevelPreference.selected()", VIEW)
        self.assertIn("selectedPreview = PlannedProtectionTier", VIEW)
        self.assertIn("Active protection remains Built-in.", VIEW)
        for forbidden in (
            "UserDefaults", "SelectedProtectionProfilePreference",
            "NSWorkspace", "FileManager", "scan-and-open",
            "Toggle(", "Picker(", "save(",
        ):
            self.assertNotIn(forbidden, VIEW)

    def test_ci_requires_real_macos_swift_and_python_checks(self):
        self.assertIn("tests/general/reset-protection-settings.py -v", CI)
        self.assertIn("test-reset-protection-settings.swift", CI)
        self.assertIn("macos-build:", CI)
        self.assertTrue((ROOT / "test-reset-protection-settings.swift").exists())


if __name__ == "__main__":
    unittest.main()
