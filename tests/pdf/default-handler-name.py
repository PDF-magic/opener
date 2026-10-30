#!/usr/bin/env python3
"""Guard the generic PDF default-handler utility name and its existing behavior."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent
NEW_NAME = "set-pdf-default-handler.swift"
OLD_NAME = "set-brave-pdf-default.swift"


class DefaultPDFHandlerNameTests(unittest.TestCase):
    def test_utility_is_renamed_without_changing_default_behavior(self):
        self.assertTrue((ROOT / NEW_NAME).is_file())
        self.assertFalse((ROOT / OLD_NAME).exists())
        source = (ROOT / NEW_NAME).read_text(encoding="utf-8")
        self.assertIn('NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.brave.Browser")', source)
        self.assertIn('CommandLine.arguments.count > 1', source)
        self.assertIn('URL(fileURLWithPath: CommandLine.arguments[1]) : brave', source)
        self.assertIn('NSWorkspace.shared.setDefaultApplication(at: handler, toOpen: .pdf)', source)
        self.assertIn('Could not set the PDF default handler:', source)

    def test_installer_invokes_renamed_utility_for_opener_bundle(self):
        installer = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
        self.assertIn('python3 "$script_dir/offer-restore-pdf-handler.py"', installer)
        self.assertIn('"$script_dir/' + NEW_NAME + '" "$app"', installer)
        self.assertNotIn('/usr/bin/swift "$script_dir/' + NEW_NAME + '" "$app"', installer)
        self.assertNotIn(OLD_NAME, installer)
        self.assertIn('app_name="PDF Magic Opener"', installer)

    def test_ci_compiles_new_utility_and_readme_uses_new_name(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('xcrun swiftc ' + NEW_NAME + ' -o "$RUNNER_TEMP/SetPDFHandler"', workflow)
        self.assertIn('python3 test-pdf-default-handler-name.py -v', workflow)
        self.assertIn('swift ' + NEW_NAME, readme)
        self.assertIn('|' + ' `' + NEW_NAME + '`' + ' |', readme)
        self.assertNotIn(OLD_NAME, workflow)
        self.assertNotIn(OLD_NAME, readme)


if __name__ == "__main__":
    unittest.main()
