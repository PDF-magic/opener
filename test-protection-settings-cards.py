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

  def test_maximum_preview_distinguishes_original_from_safe_copy_without_activation(self):
    # The current interface has a real, accessible comparison, but it is
    # exclusively a read-only preview of the unavailable Maximum tier.
    self.assertRegex(
        self.source,
        r"if selectedPreview == \.maximum \{\s*MaximumOriginalSafeCopyComparison\(\)")
    self.assertEqual(self.source.count("MaximumOriginalSafeCopyComparison()"), 1)
    comparison = self.source.split(
        "private struct MaximumOriginalSafeCopyComparison: View {", 1)[1].split(
        "\nstruct ProtectionSettingsView: View {", 1)[0]
    for label in (
        'Text("Original versus generated safe copy")',
        'Text("Original PDF")',
        'Text("Generated safe copy")',
        'maximumOriginalPDFIdentity',
        'maximumGeneratedSafeCopyIdentity',
        'maximumOriginalSafeCopyComparison',
        "not the untouched original",
        "requires its own fresh scan before opening",
        "Maximum remains unavailable",
        ".accessibilityElement(children: .combine)",
        ".fixedSize(horizontal: false, vertical: true)",
    ):
      with self.subTest(label=label):
        self.assertIn(label, comparison)
    for forbidden in (
        "Button(", "Toggle(", "onOpenURL", "FileManager", "UserDefaults",
        "URLSession", "Process(", "launch_clean_file", "scan_and_open",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, comparison)

  def test_origin_comparison_does_not_replace_verified_generated_copy_identity(self):
    root = Path(__file__).resolve().parent
    offer = (root / "maximum_sanitized_copy.py").read_text(encoding="utf-8")
    route = (root / "maximum_safe_copy_handoff.py").read_text(encoding="utf-8")
    for source in (offer, route):
      self.assertIn('"contentOrigin": GENERATED_CONTENT_ORIGIN', source)
      self.assertIn('"isUntouchedOriginal": False', source)
    self.assertIn('GENERATED_CONTENT_ORIGIN = "generatedContent"', offer)
    self.assertIn('Active protection: Built-in ClamAV', self.source)
    explanation = (root / "docs/maximum/original-safe-copy-interface.md").read_text(
        encoding="utf-8")
    self.assertIn("read-only", explanation)
    self.assertIn("original", explanation)
    self.assertIn("generated", explanation)
    ci = CI.read_text(encoding="utf-8")
    self.assertIn("python3 test-protection-settings-cards.py -v", ci)

  def test_maximum_save_action_is_gated_and_never_activates_unavailable_policy(self):
    # The preview offers a real SwiftUI Button with an injectable trusted
    # handler, but the installed Settings page cannot invent a verified PDF.
    self.assertIn("struct MaximumSanitizedPDFSaveControl: View {", self.source)
    control = self.source.split("struct MaximumSanitizedPDFSaveControl: View {", 1)[1].split(
        "\nstruct ProtectionSettingsView: View {", 1)[0]
    for marker in (
        "let verifiedOfferAvailable: Bool",
        "let onSaveRequested: (() -> Void)?",
        'Button("Save Sanitized PDF")',
        "guard verifiedOfferAvailable, let onSaveRequested else { return }",
        "onSaveRequested()",
        ".disabled(!verifiedOfferAvailable || onSaveRequested == nil)",
        'accessibilityIdentifier("maximumSaveSanitizedPDFAction")',
        'accessibilityIdentifier("maximumSaveSanitizedPDFAvailability")',
        "fresh malware scan", "does not open the file",
    ):
      with self.subTest(marker=marker):
        self.assertIn(marker, control)
    self.assertIn("if selectedPreview == .maximum {\n                  MaximumSanitizedPDFSaveControl(", self.source)
    self.assertIn("verifiedOfferAvailable: false,", self.source)
    self.assertIn("onSaveRequested: nil", self.source)
    self.assertEqual(self.source.count("MaximumSanitizedPDFSaveControl("), 1)
    # No direct file or policy changes in a settings preview.
    self.assertNotIn("Process(", control)
    self.assertNotIn("FileManager", control)
    self.assertNotIn("UserDefaults", control)

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
