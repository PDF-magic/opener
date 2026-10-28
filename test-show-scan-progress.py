#!/usr/bin/env python3
"""Guard the Show Scan Progress toggle's persistence and scan-gate separation."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
APP = ROOT / "PDFMagicOpenerApp"
PREF = APP / "ScanProgressPreference.swift"
GENERAL = APP / "GeneralSettingsView.swift"
OPENER = ROOT / "brave-pdf-opener.swift"


class ShowScanProgressTests(unittest.TestCase):
  def test_general_exposes_one_explicit_toggle_with_visible_help(self):
    source = GENERAL.read_text(encoding="utf-8")
    self.assertIn('Toggle("Show Scan Progress", isOn: Binding(', source)
    self.assertIn('set: { updateScanProgressPreference($0) }', source)
    self.assertIn('get: { showScanProgress }', source)
    self.assertIn('.accessibilityIdentifier("showScanProgressToggle")', source)
    self.assertIn('.accessibilityIdentifier("showScanProgressSection")', source)
    self.assertIn("ScanProgressPreference.isEnabled()", source)
    self.assertIn("ScanProgressPreference.save(enabled)", source)
    self.assertIn(".onAppear(perform: loadScanProgressPreference)", source)
    self.assertIn("hides only that window, including its Cancel button", source)
    self.assertIn("quarantine protection, and failure warnings remain active", source)
    self.assertIn('Picker("Browser for scanned PDFs"', source)
    self.assertIn("PDFDefaultApplicationSettingsView()", source)
    load = source.split("private func loadScanProgressPreference()", 1)[1].split(
        "private func updateScanProgressPreference", 1)[0]
    self.assertNotIn(".save(", load, "Loading preferences must never write a setting")

  def test_shared_suite_preserves_visible_default_and_avoids_scan_policy(self):
    preference = PREF.read_text(encoding="utf-8")
    self.assertIn('suiteName = "local.studio.pdf-magic-opener"', preference)
    self.assertIn('key = "showScanProgress"', preference)
    self.assertIn("let setting = defaults.object(forKey: key) as? Bool", preference)
    self.assertIn("static let showScanProgress = true", preference)
    self.assertIn("return SupportedPreferenceDefaults.showScanProgress", preference)
    self.assertIn("defaults.set(enabled, forKey: key)", preference)
    self.assertIn("defaults.synchronize()", preference)
    for disallowed in ("target-app.txt", "scan-and-open", "clamscan", "Process(",
                       "NSWorkspace", "LSSetDefault", "quarantine", "clean-scan"):
      with self.subTest(disallowed=disallowed):
        self.assertNotIn(disallowed, preference)

  def test_native_opener_only_gates_presentation_not_scan(self):
    src = OPENER.read_text(encoding="utf-8")
    presentation = src.split("private func showProgress() {", 1)[1].split(
        "private func startQueuedScans()", 1)[0]
    self.assertIn("guard ScanProgressPreference.isEnabled() else {", presentation)
    self.assertIn("panel?.orderOut(nil)", presentation)
    self.assertIn("panel = ScanProgressPanel(", presentation)
    self.assertIn("panel?.show(documentDescription: description, stage: stage,", presentation)
    self.assertIn("activeScans: launchedScans.count)", presentation)
    self.assertIn("if !launchedScans.isEmpty", presentation)
    self.assertIn("queued.append(path)", src)
    self.assertIn("startQueuedScans()", src)
    self.assertIn("startScan(path)", src)
    self.assertIn("process.executableURL = URL(fileURLWithPath: \"/bin/bash\")", src)
    self.assertNotIn("ScanProgressPreference", src.split(
        "private func startQueuedScans()", 1)[1],
        "Progress preference must not control queue, scanner, warning or launch decisions")

  def test_both_targets_build_the_shared_preference(self):
    project = (ROOT / "PDFMagicOpener.xcodeproj/project.pbxproj").read_text(encoding="utf-8")
    installer = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    self.assertIn("path = ScanProgressPreference.swift;", project)
    self.assertIn("fileRef = B20000000000000000000002;", project)
    phase = project.split("isa = PBXSourcesBuildPhase;", 1)[1].split(
        "runOnlyForDeploymentPostprocessing", 1)[0]
    self.assertIn("B20000000000000000000001,", phase)
    self.assertIn('"$script_dir/PDFMagicOpenerApp/ScanProgressPreference.swift"', installer)
    self.assertIn("test-show-scan-progress.py -v", ci)
    self.assertIn("test-show-scan-progress.swift", ci)
    self.assertIn("test-native-hidden-scan-progress.py", ci)
    self.assertIn("brave-pdf-opener.swift scan-progress-view.swift PDFMagicOpenerApp/ScanProgressPreference.swift", ci)


if __name__ == "__main__":
  unittest.main()
