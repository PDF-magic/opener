#!/usr/bin/env python3
"""Verify per-result read-only inspection is explicit, bounded and safe."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
PAGE = (ROOT / "PDFMagicOpenerApp/PrivacyAndLogsSettingsView.swift").read_text()
DETAIL = (ROOT / "PDFMagicOpenerApp/ScanHistoryResultDetailView.swift").read_text()
MODEL = (ROOT / "PDFMagicOpenerApp/RecentScanHistory.swift").read_text()
PROJECT = (ROOT / "PDFMagicOpener.xcodeproj/project.pbxproj").read_text()
CI = (ROOT / ".github/workflows/ci.yml").read_text()


class IndividualResultInspectionTests(unittest.TestCase):
  def test_user_action_selects_an_existing_validated_row(self):
    for needle in (
      "ForEach(rows) { row in", "inspectedResult = row", "inspectedResult = nil",
      ".sheet(item: $inspectedResult) { row in",
      "ScanHistoryResultDetailView(row: row)",
      'accessibilityLabel("Inspect \\(row.statusLabel) result")',
      'accessibilityIdentifier("inspectScanHistoryResult-\\(row.id)")',
      "recentScanHistory = RecentScanHistoryReader.load()",
    ):
      with self.subTest(needle=needle):
        self.assertIn(needle, PAGE)
    self.assertNotIn(".onAppear", PAGE)
    self.assertEqual(PAGE.count("RecentScanHistoryReader.load()"), 1)

  def test_detail_shows_only_safe_metadata_and_no_launch_claim(self):
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

  def test_reader_only_provides_existing_bounded_and_validated_metadata(self):
    self.assertIn("struct RecentScanHistoryRow: Identifiable", MODEL)
    self.assertIn("maximumResults = 20", MODEL)
    self.assertIn("SQLITE_OPEN_READONLY", MODEL)
    self.assertIn("SQLITE_OPEN_NOFOLLOW", MODEL)
    self.assertIn("hasExactSchema(database)", MODEL)
    self.assertIn("statuses.contains(status)", MODEL)
    self.assertIn('profile == "built-in"', MODEL)
    self.assertIn('case "clean": return "Clean scan (opening not verified)"', MODEL)

  def test_compiled_target_and_required_ci(self):
    self.assertEqual(PROJECT.count("path = ScanHistoryResultDetailView.swift;"), 1)
    self.assertIn("fileRef = B21300000000000000000002;", PROJECT)
    sources = PROJECT.split("isa = PBXSourcesBuildPhase;", 1)[1].split(
      "runOnlyForDeploymentPostprocessing", 1
    )[0]
    self.assertIn("B21300000000000000000001,", sources)
    self.assertIn("tests/scan/individual-result-inspection.py -v", CI)
    self.assertIn("scanner-tests:", CI)
    self.assertIn("macos-build:", CI)


if __name__ == "__main__":
  unittest.main()
