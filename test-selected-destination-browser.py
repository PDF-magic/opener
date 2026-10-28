#!/usr/bin/env python3
"""Prevent the scan-panel browser label from changing scan policy or saved settings."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
PANEL = (ROOT / "scan-progress-view.swift").read_text(encoding="utf-8")
OPENER = (ROOT / "brave-pdf-opener.swift").read_text(encoding="utf-8")
PREFERENCES = (ROOT / "PDFMagicOpenerApp/DefaultPDFBrowserPreferences.swift").read_text(encoding="utf-8")
CI = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")


class DestinationBrowserDisplayTests(unittest.TestCase):
  def test_progress_shows_current_read_only_selection(self):
    self.assertIn("enum SelectedDestinationBrowser", PANEL)
    self.assertIn("destinationBrowserLabel = NSTextField", PANEL)
    self.assertIn('"Destination browser: \\(displayName)"', PANEL)
    self.assertIn("destinationBrowserLabel.setAccessibilityLabel", PANEL)
    self.assertIn("panel?.updateDestinationBrowser(SelectedDestinationBrowser.displayName())", OPENER)
    presentation = OPENER.split("private func showProgress() {", 1)[1].split(
        "private func startQueuedScans()", 1)[0]
    self.assertIn("guard ScanProgressPreference.isEnabled() else {", presentation)
    self.assertIn("panel?.show(documentDescription: description, stage: stage,", presentation)
    self.assertNotIn("process.run()", presentation)
    self.assertNotIn("Process()", presentation)

  def test_display_uses_the_verified_selection_contract_and_preserves_safety(self):
    self.assertIn('openat(parent, "target-app.txt", O_RDONLY | O_NOFOLLOW', PANEL)
    self.assertIn("O_DIRECTORY | O_NOFOLLOW", PANEL)
    self.assertIn("fstat(file, &info)", PANEL)
    self.assertIn("count <= 256", PANEL)
    self.assertIn('identifier == "system-default-browser"', PANEL)
    self.assertIn('return errno == ENOENT ? "Brave" : "Unavailable"', PANEL)
    self.assertIn('identifier != "local.studio.brave-pdf-opener"', PANEL)
    self.assertIn("Custom application (", PANEL)
    self.assertIn("return nil", PREFERENCES)
    self.assertIn("saveVerified(_ option:", PREFERENCES)
    for side_effect in ("Process()", "NSWorkspace.shared.open", "write(to:", "renameat(",
                        "defaults.set(", "quarantine", "clamscan"):
      self.assertNotIn(side_effect, PANEL)
    self.assertIn("test-scan-progress-component.py -v", CI)
    self.assertIn("test-selected-destination-browser.py -v", CI)


if __name__ == "__main__":
  unittest.main()
