#!/usr/bin/env python3
"""Portable tests of actionable, read-only installation prerequisite reporting."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    "installation_prerequisites", ROOT / "scripts/report_install_prerequisites.py"
)
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


class InstallationPrerequisiteTests(unittest.TestCase):
    def check(self, *, system="darwin", version="13.0", workflow=True,
              missing_tools=(), compiler=True, scanner=True, brew=True):
        return reporter.report_prerequisites(
            system=system, version=version, workflow_available=workflow,
            executable=lambda path: path not in missing_tools,
            compiler_available=compiler,
            scanner_available=scanner, homebrew_available=brew,
        )

    def test_ready_install_reports_no_missing_items(self):
        self.assertEqual(self.check(), ((), ()))

    def test_unsupported_system_and_unverifiable_macos_version(self):
        for system, version in (("linux", ""), ("darwin", "12.7"),
                                ("darwin", ""), ("darwin", "unknown")):
            with self.subTest(system=system, version=version):
                errors, _ = self.check(system=system, version=version)
                self.assertTrue(any("macOS" in item for item in errors))

    def test_missing_finder_action_names_recovery(self):
        errors, _ = self.check(workflow=False)
        self.assertEqual(len(errors), 1)
        self.assertIn("Finder Quick Action", errors[0])
        self.assertIn("Install", errors[0])

    def test_each_missing_native_tool_is_identified_and_actionable(self):
        for path, _ in reporter.TOOLS:
            with self.subTest(tool=path):
                errors, _ = self.check(missing_tools=(path,))
                self.assertEqual(len(errors), 1)
                self.assertIn("missing", errors[0])
                self.assertIn("retry", errors[0])

    def test_missing_compiler_explains_command_line_tools(self):
        errors, _ = self.check(compiler=False)
        self.assertEqual(len(errors), 1)
        self.assertIn("xcode-select --install", errors[0])

    def test_existing_clamav_does_not_require_homebrew(self):
        self.assertEqual(self.check(scanner=True, brew=False), ((), ()))

    def test_missing_clamav_with_homebrew_is_a_nonblocking_notice(self):
        errors, notices = self.check(scanner=False, brew=True)
        self.assertFalse(errors)
        self.assertEqual(len(notices), 1)
        self.assertIn("Homebrew", notices[0])

    def test_missing_clamav_and_homebrew_explains_both_options(self):
        errors, notices = self.check(scanner=False, brew=False)
        self.assertFalse(notices)
        self.assertEqual(len(errors), 1)
        self.assertIn("ClamAV and Homebrew", errors[0])
        self.assertIn("supported ClamAV scanner", errors[0])

    def test_reports_all_missing_prerequisites_without_raw_diagnostics(self):
        errors, _ = self.check(
            workflow=False, compiler=False, scanner=False, brew=False,
            missing_tools=("/usr/bin/codesign", "/bin/launchctl"),
        )
        self.assertEqual(len(errors), 5)
        for message in errors:
            self.assertNotIn("/Users/", message)
            self.assertNotIn("/private/", message)
        self.assertEqual(len(set(errors)), len(errors))

    def test_compiler_probe_is_bounded_and_does_not_echo_untrusted_output(self):
        class Result:
            returncode = 1
            stdout = "/Users/secret/location"
        with patch.object(reporter.subprocess, "run", return_value=Result()) as run:
            self.assertFalse(reporter.swift_compiler_ready())
            run.assert_called_once_with(
                ["/usr/bin/xcrun", "--find", "swiftc"],
                capture_output=True, text=True, timeout=10, check=False,
            )
        with patch.object(reporter.subprocess, "run",
                          side_effect=OSError("sensitive path")):
            self.assertFalse(reporter.swift_compiler_ready())

    def test_cli_is_read_only_and_has_fixed_actionable_output(self):
        with patch.object(reporter.sys, "platform", "darwin"), \
             patch.object(reporter.platform, "mac_ver", return_value=("13.0", (), "")), \
             patch.object(reporter.Path, "home") as home, \
             patch.object(reporter, "executable_file", return_value=False), \
             patch.object(reporter, "detect_homebrew", return_value=None), \
             patch.object(reporter, "swift_compiler_ready") as compiler:
            home.return_value = ROOT / "synthetic-home"
            error = io.StringIO()
            output = io.StringIO()
            with redirect_stderr(error), redirect_stdout(output):
                code = reporter.main()
            self.assertEqual(code, 1)
            self.assertIn("missing prerequisites", error.getvalue())
            self.assertIn("ClamAV and Homebrew", error.getvalue())
            self.assertIn("Finder Quick Action", error.getvalue())
            compiler.assert_not_called()

    def test_installer_preflights_before_mutation_and_keeps_existing_safety(self):
        installer = (ROOT / "install-allow-and-open.sh").read_text()
        self.assertIn('scripts/report_install_prerequisites.py', installer)
        preflight = installer.index('scripts/report_install_prerequisites.py')
        self.assertLess(preflight, installer.index('signature_update_launchagent.py'))
        self.assertLess(preflight, installer.index('scripts/migration_state.py'))
        self.assertLess(preflight, installer.index('brew_executable='))
        self.assertIn('scripts/detect_homebrew.py', installer)
        self.assertIn('scripts/reconcile_pdf_handler_registration.py', installer)
        self.assertIn('python3 "$script_dir/offer-restore-pdf-handler.py"', installer)
        self.assertIn('if [ ! -f "$workflow" ]; then', installer)
        self.assertIn('command -v python3', installer)
        self.assertIn('python3 "$script_dir/scripts/report_install_prerequisites.py"', installer)
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("tests/general/installation-prerequisites.py -v", workflow)


if __name__ == "__main__":
    unittest.main()
