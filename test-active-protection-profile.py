#!/usr/bin/env python3
"""Contract for the progress panel's truthful, read-only protection profile."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class ActiveProtectionProfileTests(unittest.TestCase):
  def test_progress_panel_displays_the_actual_mandatory_policy(self):
    view = (ROOT / "scan-progress-view.swift").read_text(encoding="utf-8")
    self.assertIn('static let name = "Built-in"', view)
    self.assertIn('static let details = "ClamAV malware scanning · fail-closed"', view)
    self.assertIn('labelWithString: "Active protection profile: " + BuiltInProtectionProfile.name', view)
    self.assertIn('protectionProfileLabel.setAccessibilityLabel(protectionProfileLabel.stringValue)', view)
    self.assertIn('contentView?.addSubview(protectionProfileLabel)', view)
    self.assertIn('contentView?.addSubview(protectionProfileDetailsLabel)', view)
    self.assertNotIn("UserDefaults", view)
    self.assertNotIn("Process()", view)
    self.assertNotIn("NSTextField(string:", view)

  def test_profile_describes_the_existing_fail_closed_scan_gate(self):
    engine = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
    self.assertIn("def scanner_path(*, require_supported_version=False):", engine)
    self.assertIn("if require_supported_version:", engine)
    self.assertIn("require_supported_scanner_version(scanner)", engine)
    self.assertEqual(engine.count("scanner_path(require_supported_version=True)"), 2)
    self.assertIn("'ClamAV is unavailable.", engine)
    self.assertIn("'--alert-exceeds-max=yes', '--alert-encrypted=yes'", engine)
    self.assertIn("if not cached_clean(cache_id):", engine)
    native = (ROOT / "brave-pdf-opener.swift").read_text(encoding="utf-8")
    self.assertIn("guard ScanProgressPreference.isEnabled() else {", native)
    self.assertIn("panel = ScanProgressPanel(", native)
    self.assertIn("process.arguments = [script.path, path]", native)
    self.assertNotIn("PDF_MAGIC_PROTECTION_PROFILE", native)

  def test_ci_includes_structural_and_executable_native_coverage(self):
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    self.assertIn("python3 test-active-protection-profile.py -v", workflow)
    self.assertIn("python3 test-scan-progress-component.py -v", workflow)
    harness = (ROOT / "test-scan-progress-component.py").read_text(encoding="utf-8")
    self.assertIn("panel.protectionProfileLabel.stringValue", harness)
    self.assertIn("panel.protectionProfileDetailsLabel.stringValue", harness)
    self.assertIn('panel.cancelButton.performClick(nil)', harness)


if __name__ == "__main__":
  unittest.main()
