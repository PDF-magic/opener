#!/usr/bin/env python3
"""Read-only legacy application discovery contract (opener-0933)."""

import importlib.util
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
DETECTOR = ROOT / "scripts/detect_existing_installations.py"
spec = importlib.util.spec_from_file_location("existing_installations", DETECTOR)
detector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(detector)


class ExistingInstallationDetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.applications = Path(self.temp.name) / "Applications"
        self.applications.mkdir()

    def app(self, name, identifier):
        app = self.applications / name
        (app / "Contents").mkdir(parents=True)
        with (app / "Contents/Info.plist").open("wb") as stream:
            plistlib.dump({"CFBundleIdentifier": identifier}, stream)
        return app

    def detect(self):
        return detector.detect_existing_installations([self.applications])

    def test_recognizes_legacy_name_and_both_real_application_ids(self):
        legacy = self.app("Open PDFs in Brave.app", "local.studio.brave-pdf-opener")
        handler = self.app("PDF Magic Opener.app", "local.studio.brave-pdf-opener")
        preferences = self.app("PDFMagicOpener.app", "local.studio.pdfmagicopener.swiftui")
        renamed = self.app("Custom Legacy Name.app", "local.studio.brave-pdf-opener")
        found = {entry["path"]: entry for entry in self.detect()}
        self.assertEqual(set(found), {str(legacy), str(handler), str(preferences), str(renamed)})
        self.assertTrue(all(entry["status"] == "recognized" for entry in found.values()))
        self.assertTrue(found[str(legacy)]["legacy_name"])
        self.assertFalse(found[str(preferences)]["legacy_name"])

    def test_named_candidates_are_unverified_without_matching_identity(self):
        foreign = self.app("Open PDFs in Brave.app", "com.example.unrelated")
        malformed = self.app("PDFMagicOpener.app", "com.example.other")
        (malformed / "Contents/Info.plist").write_text("not a plist")
        self.app("Unrelated.app", "com.example.unrelated")
        found = {item["path"]: item for item in self.detect()}
        self.assertEqual(set(found), {str(foreign), str(malformed)})
        self.assertEqual(found[str(foreign)]["bundle_identifier"], "com.example.unrelated")
        self.assertEqual(found[str(foreign)]["status"], "unverified_candidate")
        self.assertIsNone(found[str(malformed)]["bundle_identifier"])

    def test_does_not_follow_bundle_or_info_plist_symlinks(self):
        target = self.app("Outside.app", "local.studio.brave-pdf-opener")
        legacy_link = self.applications / "Open PDFs in Brave.app"
        legacy_link.symlink_to(target, target_is_directory=True)
        named = self.app("PDF Magic Opener.app", "local.studio.brave-pdf-opener")
        info = named / "Contents/Info.plist"
        info.unlink()
        info.symlink_to(target / "Contents/Info.plist")
        found = {entry["path"]: entry for entry in self.detect()}
        self.assertEqual(found[str(legacy_link)]["status"], "unverified_candidate")
        self.assertIsNone(found[str(legacy_link)]["bundle_identifier"])
        self.assertEqual(found[str(named)]["status"], "unverified_candidate")
        self.assertEqual(found[str(target)]["status"], "recognized")

    def test_rejects_oversized_plists_and_skips_symlinked_search_roots(self):
        named = self.app("Open PDFs in Brave.app", "local.studio.brave-pdf-opener")
        (named / "Contents/Info.plist").write_bytes(b"x" * (detector.MAX_PLIST_BYTES + 1))
        link = Path(self.temp.name) / "Applications-link"
        link.symlink_to(self.applications, target_is_directory=True)
        self.assertEqual(detector.detect_existing_installations([link]), [])
        self.assertEqual(self.detect()[0]["status"], "unverified_candidate")

    def test_cli_is_read_only_and_outputs_machine_readable_inventory(self):
        app = self.app("Open PDFs in Brave.app", "local.studio.brave-pdf-opener")
        info = app / "Contents/Info.plist"
        before = info.read_bytes()
        process = subprocess.run([sys.executable, str(DETECTOR),
                                  "--applications-dir", str(self.applications)],
                                 capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(process.stdout)[0]["path"], str(app))
        self.assertEqual(info.read_bytes(), before)
        self.assertTrue(app.is_dir())

    def test_ids_match_current_repository_metadata(self):
        installer = (ROOT / "install-allow-and-open.sh").read_text()
        project = (ROOT / "PDFMagicOpener.xcodeproj/project.pbxproj").read_text()
        self.assertIn("local.studio.brave-pdf-opener", installer)
        self.assertIn("local.studio.pdfmagicopener.swiftui", project)
        self.assertEqual(detector.APPLICATION_IDENTIFIERS, {
            "local.studio.brave-pdf-opener", "local.studio.pdfmagicopener.swiftui"
        })


if __name__ == "__main__":
    unittest.main()
