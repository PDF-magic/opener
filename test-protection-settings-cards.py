#!/usr/bin/env python3
"""opener-0327: three accessible preview-selectable protection cards, no policy switch."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent
VIEW = ROOT / "PDFMagicOpenerApp" / "ProtectionSettingsView.swift"
NAVIGATION = ROOT / "PDFMagicOpenerApp" / "MainPreferencesView.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"
CI = ROOT / ".github" / "workflows" / "ci.yml"


class ProtectionCardsTests(unittest.TestCase):
  def setUp(self):
    self.source = VIEW.read_text(encoding="utf-8")

  def test_exactly_three_planned_tier_cards(self):
    declaration = self.source.split("private enum PlannedProtectionTier:", 1)[1].split(
        "  var id:", 1)[0]
    self.assertEqual(
        re.findall(r"^  case (\w+)$", declaration, re.MULTILINE),
        ["standard", "enhanced", "maximum"])
    self.assertIn("CaseIterable", declaration)
    for title in ("Standard", "Enhanced", "Maximum"):
      self.assertIn(f'return "{title}"', self.source)
    self.assertIn("ForEach(PlannedProtectionTier.allCases)", self.source)
    self.assertIn('GroupBox("Planned protection levels")', self.source)

  def test_tapping_cards_updates_single_selection_and_detail_panel(self):
    # Real Buttons, not inert decoration or three independently checked toggles.
    self.assertIn("Button {", self.source)
    self.assertIn("@State private var selectedPreview: PlannedProtectionTier?", self.source)
    self.assertIn("selectedPreview = tier", self.source)
    self.assertIn("selectedPreview == tier", self.source)
    self.assertIn("if let selectedPreview {", self.source)
    self.assertIn("Text(selectedPreview.detail)", self.source)
    self.assertIn("protectionCardPreviewDetail", self.source)
    for forbidden in ("Toggle(", "Picker(", "Slider(", "selectedPreview = .standard"):
      self.assertNotIn(forbidden, self.source)

  def test_controls_are_accessible_and_usable_at_large_text_sizes(self):
    for marker in (
        '.buttonStyle(.plain)',
        'accessibilityIdentifier("protectionCard-\\(tier.rawValue)")',
        'accessibilityLabel("\\(tier.title) protection preview")',
        "accessibilityValue(selectedPreview == tier",
        'accessibilityHint("Show \\(tier.title) details.',
        '.accessibilityIdentifier("activeBuiltInProtection")',
        'accessibilityIdentifier("plannedProtectionCardsSection")',
        ".fixedSize(horizontal: false, vertical: true)",
        "ScrollView {",
    ):
      with self.subTest(marker=marker):
        self.assertIn(marker, self.source)
    for forbidden in (".frame(width:", ".frame(height:", ".lineLimit(1)"):
      self.assertNotIn(forbidden, self.source)

  def test_previews_do_not_pretend_to_activate_unimplemented_tiers(self):
    self.assertIn("Active protection: Built-in ClamAV", self.source)
    self.assertIn("Preview only · Not available as an active policy", self.source)
    self.assertIn("choosing a card does not enable it", self.source)
    self.assertIn("This does not change scanning.", self.source)
    for title in ("Standard", "Enhanced", "Maximum"):
      self.assertIn(f'case .{title.lower()}:', self.source)
    for forbidden in (
        "UserDefaults", "@AppStorage", "SelectedProtectionProfilePreference",
        "FileManager", "Process(", "NSWorkspace", "FileHandle(",
        "scan-and-open", "clamscan", "LSSetDefault", "write(to:",
        "onOpenURL", "setDefault", "URLSession", "save(",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, self.source)

  def test_builtin_scanner_and_planned_profile_catalog_remain_authoritative(self):
    from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
    self.assertEqual(set(PROTECTION_PROFILES), {
        ProtectionProfileID.STANDARD,
        ProtectionProfileID.ENHANCED,
        ProtectionProfileID.MAXIMUM})
    self.assertTrue(all(not definition.selectable
                        for definition in PROTECTION_PROFILES.values()))
    scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
    self.assertIn("if not cached_clean(cache_id):", scanner)
    self.assertNotIn("PlannedProtectionTier", scanner)
    stored = (ROOT / "test-selected-protection-profile.swift").read_text(encoding="utf-8")
    self.assertIn("SelectedProtectionProfilePreference.selected(defaults: defaults) == .builtIn", stored)

  def test_maximum_preview_explains_capability_loss_without_enabling_it(self):
    # A visible, labelled explanation belongs only to the Maximum preview.
    tier = self.source.split("private enum PlannedProtectionTier:", 1)[1].split(
        "struct ProtectionSettingsView: View {", 1)[0]
    self.assertIn("var capabilityLossExplanation: String?", tier)
    self.assertIn("guard self == .maximum else { return nil }", tier)
    notice = tier.split("var capabilityLossExplanation: String?", 1)[1].split(
        "\n  }", 1)[0]
    for phrase in (
        "flattened page images", "selectable and searchable text",
        "clickable links", "interactive form fields",
        "annotations and comments", "embedded attachments",
        "document metadata", "scripts or other active PDF actions",
        "Digital signatures may be invalidated", "visual details can change",
        "OCR is not restored", "untouched original",
        "not a malware-clean verdict", "separate fresh scan",
    ):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase, notice)

    self.assertIn(
        "if let capabilityLoss = selectedPreview.capabilityLossExplanation {",
        self.source)
    self.assertEqual(
        self.source.count("if let capabilityLoss = selectedPreview.capabilityLossExplanation {"), 1)
    self.assertIn('Text("PDF capabilities that may be removed")', self.source)
    self.assertIn("Text(capabilityLoss)", self.source)
    self.assertIn('.accessibilityIdentifier("maximumCapabilityLossExplanation")',
                  self.source)
    self.assertIn(".accessibilityAddTraits(.isHeader)", self.source)
    self.assertIn(".fixedSize(horizontal: false, vertical: true)", self.source)
    # Existing scanner CI and the native macOS build exercise the new display.
    ci = CI.read_text(encoding="utf-8")
    self.assertIn("python3 test-protection-settings-cards.py -v", ci)
    self.assertIn("macos-build:", ci)

  def test_existing_preferences_and_native_target_remain_wired(self):
    nav = NAVIGATION.read_text(encoding="utf-8")
    project = PROJECT.read_text(encoding="utf-8")
    self.assertIn("case .security:", nav)
    self.assertIn("ProtectionSettingsView()", nav)
    self.assertIn("path = ProtectionSettingsView.swift;", project)
    self.assertIn("A10000000000000000000022", project)
    for marker in (
        'GroupBox("Malware scanning")',
        'GroupBox("Unsafe or unverified files")',
        'GroupBox("Verified application handoff")',
        'accessibilityIdentifier("protectionSettingsPage")',
    ):
      self.assertIn(marker, self.source)

  def test_ci_runs_cards_and_full_native_build(self):
    ci = CI.read_text(encoding="utf-8")
    self.assertIn("python3 test-protection-settings-cards.py -v", ci)
    self.assertIn("macos-build:", ci)
    self.assertIn("test-main-preferences-window.py -v", ci)
    self.assertIn("test-technical-preferences-help.py -v", ci)


if __name__ == "__main__":
  unittest.main()
