#!/usr/bin/env python3
"""Check the opt-in macOS PDF-default action without modifying file associations."""

from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent


class PDFDefaultUserActionTests(unittest.TestCase):
    def test_finder_action_is_explicit_and_never_uses_untrusted_app_paths(self):
        script = ROOT / "make-pdf-magic-default.command"
        self.assertTrue(script.is_file())
        source = script.read_text()
        self.assertTrue(source.startswith("#!/bin/bash\nset -euo pipefail\n"))
        self.assertIn('helper="$HOME/Applications/PDF Magic Opener.app/Contents/MacOS/MakePDFMagicDefault"', source)
        self.assertIn('if [ ! -x "$helper" ]; then', source)
        self.assertIn('exec "$helper"', source)
        self.assertNotIn("target-app.txt", source)
        self.assertNotIn("set-pdf-default-handler.swift", source)
        subprocess.run(["bash", "-n", str(script)], check=True)

    def test_installer_exposes_action_without_overwriting_existing_user_action(self):
        script = (ROOT / "install-allow-and-open.sh").read_text()
        self.assertIn('swiftc -parse-as-library -O "$script_dir/make-pdf-magic-default.swift"', script)
        self.assertIn('"$app/Contents/MacOS/MakePDFMagicDefault"', script)
        self.assertIn('action="$HOME/Applications/Make PDF Magic Opener Default.command"', script)
        self.assertIn('if [ ! -e "$action" ] && [ ! -L "$action" ]; then', script)
        self.assertIn('cp "$script_dir/make-pdf-magic-default.command" "$action"', script)
        self.assertIn('chmod 755 "$action"', script)
        self.assertLess(script.index('MakePDFMagicDefault"'), script.index('/usr/bin/codesign --force --sign - "$app"'))

    def test_native_action_never_changes_target_app_or_scanner(self):
        source = (ROOT / "make-pdf-magic-default.swift").read_text()
        self.assertIn('let openerIdentifier = "local.studio.brave-pdf-opener"', source)
        self.assertIn('guard verifiedPDFMagicOpener(at: application)', source)
        self.assertIn('NSWorkspace.shared.setDefaultApplication(', source)
        self.assertIn('at: application, toOpen: UTType.pdf', source)
        self.assertIn('guard CommandLine.arguments.count == 1', source)
        self.assertNotIn("scan-and-open.py", source)
        self.assertNotIn("target-app.txt", source)
        self.assertNotIn("com.brave.Browser", source)

    def test_ci_runs_both_syntax_and_native_validation(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("python3 scripts/run-test.py tests/pdf/default-user-action.py -v", workflow)
        self.assertIn("make-pdf-magic-default.command", workflow)
        self.assertIn("test-make-pdf-magic-default.swift", workflow)


if __name__ == "__main__":
    unittest.main()
