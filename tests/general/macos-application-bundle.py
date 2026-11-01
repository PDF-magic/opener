#!/usr/bin/env python3
"""Guard the standalone, unsigned Release macOS bundle distribution workflow."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/macos-application-bundle.yml"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj/project.pbxproj"
HELPERS = ROOT / "scripts/package_application_helpers.py"


class MacOSApplicationBundleTests(unittest.TestCase):
  def test_shared_xcode_scheme_builds_the_separate_preferences_app(self):
    project = PROJECT.read_text(encoding="utf-8")
    scheme = (
      ROOT / "PDFMagicOpener.xcodeproj/xcshareddata/xcschemes/PDFMagicOpener.xcscheme"
    ).read_text(encoding="utf-8")
    self.assertIn('productType = "com.apple.product-type.application";', project)
    self.assertIn("local.studio.pdfmagicopener.swiftui", project)
    self.assertIn('BuildableName="PDFMagicOpener.app"', scheme)
    self.assertIn('buildForArchiving="YES"', scheme)

  def test_ci_builds_and_uploads_only_a_verified_unsigned_release_bundle(self):
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for required in (
      "pull_request:", "merge_group:", "branches: [main]",
      "runs-on: macos-latest",
      "persist-credentials: false",
      "-configuration Release", "CODE_SIGNING_ALLOWED=NO build",
      "scripts/package_application_helpers.py --app",
      'scripts/package_application_helpers.py --verify "$stage/PDFMagicOpener.app"',
      "ditto -c -k --keepParent",
      'ditto -x -k "$archive" "$extracted"',
      'scripts/package_application_helpers.py --verify "$extracted/PDFMagicOpener.app"',
      'tests/app/fresh-launch.py --app "$extracted/PDFMagicOpener.app"',
      "actions/upload-artifact@v4",
      "pdf-magic-opener-macos-unsigned.zip",
      "if-no-files-found: error",
    ):
      with self.subTest(required=required):
        self.assertIn(required, workflow)
    self.assertLess(workflow.index("-configuration Release"),
                    workflow.index("scripts/package_application_helpers.py --app"))
    self.assertLess(workflow.index('scripts/package_application_helpers.py --verify "$stage/'),
                    workflow.index("ditto -c -k --keepParent"))
    self.assertLess(workflow.index('scripts/package_application_helpers.py --verify "$extracted/'),
                    workflow.index("actions/upload-artifact@v4"))

  def test_packaging_keeps_scanner_handler_and_secrets_out(self):
    workflow = WORKFLOW.read_text(encoding="utf-8")
    package = HELPERS.read_text(encoding="utf-8")
    for forbidden in (
      "install-allow-and-open.sh",
      "codesign --sign", "notarytool", "security import", "secrets.",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, workflow)
    for executable in ("PDFOpener", "MakePDFMagicDefault"):
      self.assertIn('test ! -e "$stage/PDFMagicOpener.app/Contents/Helpers/'
                    + executable + '"', workflow)
      self.assertIn('test ! -e "$extracted/PDFMagicOpener.app/Contents/Helpers/'
                    + executable + '"', workflow)
    self.assertIn('or "CFBundleDocumentTypes" in plist', package)
    self.assertIn('NON_DISTRIBUTABLE_SUFFIXES', package)
    self.assertIn('".key", ".pem", ".p12", ".pfx"', package)


if __name__ == "__main__":
  unittest.main()
