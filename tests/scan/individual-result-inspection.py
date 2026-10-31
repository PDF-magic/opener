#!/usr/bin/env python3
"""Verify per-result read-only inspection is explicit, bounded and safe."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
PAGE = (ROOT / "PDFMagicOpenerApp/ScanHistorySettingsView.swift").read_text()
MAIN = (ROOT / "PDFMagicOpenerApp/MainPreferencesView.swift").read_text()
DETAIL = (ROOT / "PDFMagicOpenerApp/ScanHistoryResultDetailView.swift").read_text()
MODEL = (ROOT / "PDFMagicOpenerApp/RecentScanHistory.swift").read_text()
PROJECT = (ROOT / "PDFMagicOpener.xcodeproj/project.pbxproj").read_text()
CI = (ROOT / ".github/workflows/ci.yml").read_text()


class IndividualResultInspectionTests(unittest.TestCase):
  def test_explicit_opt_in_and_already_validated_in_memory_result(self):
    for needle in (
      "init(scanHistoryEnabled: Bool = false)",
      "if section != .scanHistory || scanHistoryEnabled {",
    ):
      self.assertIn(needle, MAIN)
    for needle in (
      "ForEach(rows) { row in", "inspectedResult = row", "inspectedResult = nil",
      ".sheet(item: $inspectedResult) { row in",
      "ScanHistoryResultDetailView(row: row)",
      'accessibilityLabel("Inspect \\(row.statusLabel) result")',
      'accessibilityIdentifier("inspectScanHistoryResult-\\(row.id)")',
      "recentScanHistory = RecentScanHistoryReader.load()",
      'Button("Show recent scan results")',
    ):
      with self.subTest(needle=needle):
        self.assertIn(needle, PAGE)
    self.assertNotIn(".onAppear", PAGE)
    self.assertEqual(PAGE.count("RecentScanHistoryReader.load()"), 1)

  def test_detail_shows_safe_metadata_without_unverified_launch_claim(self):
    for needle in (
      "struct ScanHistoryResultDetailView: View",
      "let row: RecentScanHistoryRow",
      'Text("Scan Result Details")',
      'GroupBox("Individual scan result")',
      'LabeledContent("Scanned", value: row.scannedAt.formatted(',
      'LabeledContent("Final scan status", value: row.statusLabel)',
      'LabeledContent("Scanner version", value: row.scannerVersion ?? "Unknown")',
      'LabeledContent("Effective protection profile", value: row.profile)',
      'LabeledContent("File opening", value: "Not verified")',
      'accessibilityIdentifier("scanHistoryIndividualMetadata")',
      'accessibilityIdentifier("scanHistoryResultDetailView")',
      'accessibilityIdentifier("closeScanHistoryDetailsButton")',
      'Button("Done") { dismiss() }',
      "does not confirm that a file was opened",
    ):
      with self.subTest(needle=needle):
        self.assertIn(needle, DETAIL)
    for forbidden in (
      "row.filename", "row.sourceURL", "row.documentText", "row.pdfContents",
      "row.attachments", "row.browsingHistory", "FileManager", "FileHandle(",
      "UserDefaults", "@AppStorage", "URLSession", "Process(", "NSWorkspace",
      "onAppear", "onOpenURL", "clamscan(", "RecentScanHistoryReader.load()",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, DETAIL)

  def test_reader_enforces_private_metadata_with_a_bounded_list(self):
    for needle in (
      "struct RecentScanHistoryRow: Identifiable", "maximumResults = 20",
      "SQLITE_OPEN_READONLY", "SQLITE_OPEN_NOFOLLOW", "hasExactSchema(database)",
      "statuses.contains(status)", 'profile == "built-in"',
      'case "clean": return "Clean scan (opening not verified)"',
    ):
      self.assertIn(needle, MODEL)

  def test_native_build_and_required_ci(self):
    self.assertEqual(PROJECT.count("path = ScanHistoryResultDetailView.swift;"), 1)
    self.assertIn("fileRef = B21300000000000000000002;", PROJECT)
    src = PROJECT.split("isa = PBXSourcesBuildPhase;", 1)[1].split(
      "runOnlyForDeploymentPostprocessing", 1
    )[0]
    self.assertIn("B21300000000000000000001,", src)
    self.assertIn("tests/scan/individual-result-inspection.py -v", CI)
    self.assertIn("macos-build:", CI)
    self.assertIn("scanner-tests:", CI)


if __name__ == "__main__":
  unittest.main()
