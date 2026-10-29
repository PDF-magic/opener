#!/usr/bin/env python3
"""opener-0352: warn before lowering a planned preview, never relax scanning."""

from pathlib import Path
import re
import unittest

from effective_protection_policy import ACTIVE_PROFILE_ID, resolve_effective_policy
from protection_exception_policy import (
    EXCEPTION_SUPPORT_DECISION, ProtectionExceptionNotSupported,
    request_protection_exception,
)
from protection_profiles import PROTECTION_PROFILES

ROOT = Path(__file__).resolve().parent
VIEW = (ROOT / "PDFMagicOpenerApp/ProtectionSettingsView.swift").read_text(
    encoding="utf-8"
)
SCANNER = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")


class LowerProtectionWarningTests(unittest.TestCase):
    def test_all_preview_downgrades_and_only_downgrades_require_warning(self):
        rank_source = VIEW.split("var previewStrength: Int {", 1)[1].split(
            "  func isLowerPreview", 1
        )[0]
        ranks = {
            tier: int(rank)
            for tier, rank in re.findall(
                r"case \.(standard|enhanced|maximum): return (\d+)",
                rank_source,
            )
        }
        self.assertEqual(ranks, {"standard": 0, "enhanced": 1, "maximum": 2})
        comparator = VIEW.split("func isLowerPreview(", 1)[1].split(
            "\n  }", 1
        )[0]
        self.assertIn("guard let current else { return false }", comparator)
        self.assertIn("previewStrength < current.previewStrength", comparator)
        warnings = [
            (current, proposed)
            for current in ranks for proposed in ranks
            if ranks[proposed] < ranks[current]
        ]
        self.assertEqual(warnings, [
            ("enhanced", "standard"),
            ("maximum", "standard"),
            ("maximum", "enhanced"),
        ])
        self.assertFalse(any(ranks[tier] < ranks[tier] for tier in ranks))

    def test_card_action_stages_downgrade_before_any_preference_write(self):
        action = VIEW.split("ForEach(PlannedProtectionTier.allCases)", 1)[1]
        action = action.split("} label: {", 1)[0]
        self.assertRegex(
            action,
            r"if tier\.isLowerPreview\(than: selectedPreview\) \{\s*"
            r"pendingLowerPreview = tier\s*"
            r"showLowerPreviewWarning = true\s*"
            r"\} else \{\s*saveProtectionPreview\(tier\)",
        )
        self.assertNotIn("saveExplicitChoice", action)
        save = VIEW.split(
            "private func saveProtectionPreview(", 1
        )[1].split("private func resetProtectionPreview()", 1)[0]
        self.assertIn("PreferredProtectionLevel(rawValue: tier.rawValue)", save)
        self.assertIn("PlannedProtectionLevelPreference.saveExplicitChoice(level)", save)
        self.assertIn("selectedPreview = tier", save)
        self.assertLess(save.index("saveExplicitChoice(level)"), save.index("selectedPreview = tier"))

    def test_alert_explains_risk_and_requires_explicit_user_action(self):
        alert = VIEW.split(
            '.alert("Lower planned protection preview?"', 1
        )[1].split(".confirmationDialog(", 1)[0]
        self.assertIn("isPresented: $showLowerPreviewWarning", alert)
        self.assertIn('Button("Keep current preview", role: .cancel)', alert)
        self.assertIn('Button("Save lower preview")', alert)
        self.assertIn("pendingLowerPreview = nil", alert)
        self.assertIn("guard let pendingLowerPreview else { return }", alert)
        self.assertIn("saveProtectionPreview(pendingLowerPreview)", alert)
        self.assertIn("fewer planned checks", alert)
        self.assertIn("does not reduce active Built-in ClamAV scanning", alert)
        self.assertIn("Protection exceptions and scan bypasses are not supported.", alert)
        self.assertNotIn("saveExplicitChoice", alert)

    def test_reset_confirmation_also_warns_about_lower_preview(self):
        reset = VIEW.split(
            '.confirmationDialog(\n      "Reset Protection Settings?"', 1
        )[1].split("private func saveProtectionPreview(", 1)[0]
        self.assertIn("isPresented: $showProtectionResetConfirmation", reset)
        self.assertIn('Button("Cancel", role: .cancel)', reset)
        self.assertIn("Resetting Enhanced or Maximum to Standard", reset)
        self.assertIn("lower planned preview with fewer checks", reset)
        self.assertIn("does not reduce active Built-in ClamAV scanning", reset)
        self.assertIn("no bypass is available", reset)

    def test_enforced_scanning_and_exception_refusal_are_unchanged(self):
        self.assertFalse(EXCEPTION_SUPPORT_DECISION.supported)
        with self.assertRaises(ProtectionExceptionNotSupported):
            request_protection_exception({"skip_scan": True})
        self.assertEqual(resolve_effective_policy().profile_id, ACTIVE_PROFILE_ID)
        self.assertTrue(all(not tier.selectable for tier in PROTECTION_PROFILES.values()))
        for forbidden in (
            "UserDefaults", "SelectedProtectionProfilePreference.save",
            "scan-and-open", "clamscan", "NSWorkspace", "Process(",
        ):
            self.assertNotIn(forbidden, VIEW)
        self.assertIn("if not cached_clean(cache_id):", SCANNER)
        self.assertIn("decision = decide_opening(detection)", SCANNER)
        self.assertIn("verify_file_integrity(path, before, identity)", SCANNER)

    def test_ci_runs_warning_regression_and_builds_actual_settings_ui(self):
        workflow = (
            ROOT / ".github/workflows/protection-lower-preview-warning.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("test-protection-lower-preview-warning.py -v", workflow)
        self.assertIn("pull_request:", workflow)
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("macos-build:", ci)
        self.assertIn("xcodebuild -project PDFMagicOpener.xcodeproj", ci)


if __name__ == "__main__":
    unittest.main()
