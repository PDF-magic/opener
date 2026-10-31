#!/usr/bin/env python3
"""Verify launch selection is independent of ClamAV and stays fail-closed."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from file_launcher import (NATIVE_LAUNCHER, PDF_DEFAULT_BUNDLE_ID, PDF_OPENER_BUNDLE_ID,
                           scanned_file_identity,
                           PDF_TARGET_VERIFIER, PDF_TARGET_UNAVAILABLE_MESSAGE,
                           PDF_TARGET_VERIFICATION_MESSAGE, launch_clean_file,
                           verify_launch_target, verify_local_file_available)


ROOT = Path(__file__).resolve().parents[2]


class FileLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        setting = patch('file_launcher.TARGET_APP_CONFIG', self.root / 'target-app.txt')
        setting.start()
        self.addCleanup(setting.stop)
        # Existing launch-routing tests mock Process execution, not installed
        # native binaries. Dedicated tests below exercise the real path gate.
        exe = patch("file_launcher.require_executable_path")
        exe.start()
        self.addCleanup(exe.stop)

    def test_pdf_uses_existing_brave_destination_even_with_uppercase_extension(self):
        pdf = self.root / "a document.PDF"
        pdf.write_bytes(b"%PDF-1.4\n")
        with patch("file_launcher.subprocess.run") as run:
            launch_clean_file(pdf)
        run.assert_called_once_with(
            [str(NATIVE_LAUNCHER), "--bundle-id", PDF_DEFAULT_BUNDLE_ID, str(pdf)], check=True
        )
        self.assertEqual(PDF_DEFAULT_BUNDLE_ID, "com.brave.Browser")

    def test_explicit_self_destination_never_runs_verification_or_launcher(self):
        pdf = self.root / "document.PDF"
        pdf.write_bytes(b"%PDF-1.4\\n")
        self.assertEqual(PDF_OPENER_BUNDLE_ID, "local.studio.brave-pdf-opener")
        with patch("file_launcher.subprocess.run") as run:
            with self.assertRaisesRegex(RuntimeError, "cannot launch itself"):
                verify_launch_target(pdf, target_app=PDF_OPENER_BUNDLE_ID)
            with self.assertRaisesRegex(RuntimeError, "cannot launch itself"):
                launch_clean_file(pdf, target_app=PDF_OPENER_BUNDLE_ID)
        run.assert_not_called()

    def test_macos_download_preflight_rejects_pending_pdf(self):
        pdf = self.root / "not yet downloaded.PDF"
        with patch("file_launcher.sys.platform", "darwin"), \
             patch("file_launcher.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 1)) as run:
            with self.assertRaisesRegex(RuntimeError, "not available locally"):
                verify_local_file_available(pdf)
        run.assert_called_once_with(
            [str(NATIVE_LAUNCHER), "--check-local", str(pdf)],
            capture_output=True, timeout=10
        )

    def test_macos_download_preflight_allows_local_pdf(self):
        with patch("file_launcher.sys.platform", "darwin"), \
             patch("file_launcher.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 0)) as run:
            verify_local_file_available(self.root / "downloaded.pdf")
        self.assertEqual(run.call_count, 1)

    def test_macos_download_preflight_fails_closed_when_helper_missing(self):
        with patch("file_launcher.sys.platform", "darwin"), \
             patch("file_launcher.subprocess.run",
                   side_effect=FileNotFoundError("not installed")):
            with self.assertRaisesRegex(RuntimeError, "not available locally"):
                verify_local_file_available(self.root / "cloud.pdf")

    def test_non_pdf_uses_system_default_application(self):
        document = self.root / "file with spaces.txt"
        document.write_text("safe")
        with patch("file_launcher.subprocess.run") as run:
            launch_clean_file(document)
        run.assert_called_once_with([str(NATIVE_LAUNCHER), str(document)], check=True)

    def test_app_bundle_uses_default_open_behavior(self):
        bundle = self.root / "Example.app"
        bundle.mkdir()
        with patch("file_launcher.subprocess.run") as run:
            launch_clean_file(bundle)
        run.assert_called_once_with([str(NATIVE_LAUNCHER), str(bundle)], check=True)

    def test_scanned_identity_is_scoped_and_sent_to_native_launcher(self):
        pdf = self.root / "report.pdf"
        pdf.write_bytes(b"%PDF-1.4\\n")
        info = pdf.lstat()
        import stat
        identity = (("", info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode),
                     info.st_size, info.st_mtime_ns, info.st_ctime_ns),)
        proof = ":".join(map(str, identity[0][1:]))
        with patch("file_launcher.subprocess.run") as run:
            with scanned_file_identity(identity):
                launch_clean_file(pdf)
            launch_clean_file(pdf)
        self.assertEqual(run.call_args_list[0].args[0],
                         [str(NATIVE_LAUNCHER), "--expected-identity", proof,
                          "--bundle-id", PDF_DEFAULT_BUNDLE_ID, str(pdf)])
        self.assertEqual(run.call_args_list[1].args[0],
                         [str(NATIVE_LAUNCHER), "--bundle-id", PDF_DEFAULT_BUNDLE_ID, str(pdf)])

    def test_invalid_identity_cannot_authorize_opening(self):
        with patch("file_launcher.subprocess.run") as run:
            with self.assertRaisesRegex(RuntimeError, "identity is invalid"):
                with scanned_file_identity((("not root", 1, 2, 3, 4, 5, 6),)):
                    launch_clean_file(self.root / "report.pdf")
        run.assert_not_called()

    def test_open_failure_is_not_swallowed(self):
        document = self.root / "file.pdf"
        with patch("file_launcher.subprocess.run",
                   side_effect=subprocess.CalledProcessError(1, str(NATIVE_LAUNCHER))):
            with self.assertRaises(subprocess.CalledProcessError):
                launch_clean_file(document)

    def test_scanner_delegates_selection_without_brave_policy(self):
        source = (ROOT / "scan-and-open.py").read_text()
        self.assertNotIn("com.brave.Browser", source)
        self.assertNotIn("PDF_DEFAULT_BUNDLE_ID", source)
        self.assertIn("launch_clean_file(path, target_app=destination if is_pdf else None)", source)
        self.assertIn("destination = intended_destination(path)", source)
        quarantine = source.index("    remove_quarantine(path)\n")
        # Quarantine stays intact, so the final identity/ctime check is strict.
        final_check = source.index(
            "    verify_file_integrity(path, before, identity)",
            quarantine)
        launch = source.index("    launch_clean_file(path, target_app=destination if is_pdf else None)", final_check)
        self.assertLess(quarantine, final_check)
        self.assertLess(final_check, launch)

    def test_native_workspace_api_routing(self):
        swift = (ROOT / "launch-scanned-file.swift").read_text()
        for name in ("NSWorkspace", "workspace.open([target], withApplicationAt:",
                     "workspace.openApplication(at: target", "workspace.open(target)"):
            self.assertIn(name, swift)

    def test_registered_pdf_handler_preflight_invokes_native_verifier(self):
        with patch("file_launcher.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 0)) as run:
            verify_launch_target(self.root / "document.PDF")
        run.assert_called_once_with(
            [str(PDF_TARGET_VERIFIER), PDF_DEFAULT_BUNDLE_ID],
            capture_output=True, timeout=10,
        )

    def test_unregistered_missing_and_timed_out_verifiers_block(self):
        for outcome in (
            subprocess.CompletedProcess([], 1),
            FileNotFoundError("verifier missing"),
            subprocess.TimeoutExpired("verifier", 10),
        ):
            with self.subTest(outcome=str(outcome)):
                kwargs = ({"return_value": outcome} if isinstance(
                    outcome, subprocess.CompletedProcess) else {"side_effect": outcome})
                with patch("file_launcher.subprocess.run", **kwargs):
                    with self.assertRaisesRegex(RuntimeError, "opening was stopped"):
                        verify_launch_target(self.root / "document.pdf")

    def test_missing_pdf_browser_explains_how_to_change_selection(self):
        path = self.root / "private-name.pdf"
        with patch("file_launcher.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 1, b"",
                                                             b"/private/secret/file.pdf")):
            with self.assertRaises(RuntimeError) as raised:
                verify_launch_target(path, target_app="com.example.Uninstalled")
        self.assertEqual(str(raised.exception), PDF_TARGET_UNAVAILABLE_MESSAGE)
        self.assertIn("target-app.txt", str(raised.exception))
        self.assertNotIn(str(path), str(raised.exception))
        self.assertNotIn("/private/secret", str(raised.exception))

    def test_missing_verification_helper_has_safe_reinstall_guidance(self):
        with patch("file_launcher.subprocess.run",
                   side_effect=FileNotFoundError("/private/secret/verifier")):
            with self.assertRaises(RuntimeError) as raised:
                verify_launch_target(self.root / "document.pdf")
        self.assertEqual(str(raised.exception), PDF_TARGET_VERIFICATION_MESSAGE)
        self.assertNotIn("/private/secret", str(raised.exception))

    def test_pinned_preflight_uses_supplied_bundle_identifier(self):
        target = self.root / "file.pdf"
        with patch("file_launcher.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 0)) as run:
            verify_launch_target(target, target_app="com.apple.Preview")
        run.assert_called_once_with(
            [str(PDF_TARGET_VERIFIER), "com.apple.Preview"],
            capture_output=True, timeout=10,
        )

    def test_non_pdf_retains_default_handler_without_verification(self):
        for path in ("readme.txt", "Another.app"):
            with self.subTest(path=path):
                with patch("file_launcher.subprocess.run") as run:
                    verify_launch_target(self.root / path)
                run.assert_not_called()

    def test_scanner_preflights_target_before_quarantine_release(self):
        source = (ROOT / "scan-and-open.py").read_text()
        self.assertIn("verify_launch_target(path, target_app=destination if is_pdf else None)", source)
        self.assertLess(source.rindex("    verify_launch_target(path, target_app=destination if is_pdf else None)"),
                        source.rindex("    remove_quarantine(path)"))

    def test_installer_deploys_launch_module_with_scanner(self):
        script = (ROOT / "install-allow-and-open.sh").read_text()
        line = next(line for line in script.splitlines()
                    if line.startswith('cp "$script_dir/allow-and-open.sh"'))
        self.assertIn('"$script_dir/scan-and-open.py"', line)
        self.assertIn('"$script_dir/file_launcher.py"', line)
        self.assertIn('"$install_dir/"', line)
        self.assertIn('swiftc -parse-as-library -O "$script_dir/verify-pdf-target.swift"', script)
        self.assertIn('"$install_dir/verify-pdf-target"', script)
        self.assertIn('swiftc -O "$script_dir/launch-scanned-file.swift"', script)
        self.assertIn('"$install_dir/launch-scanned-file"', script)



class ExecutablePathValidationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="exec-path-policy-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.executable = self.root / "native-helper"
        self.executable.write_bytes(b"#!/bin/sh\nexit 0\n")
        self.executable.chmod(0o700)
        self.alias = self.root / "native-link"
        self.alias.symlink_to(self.executable)
        self.blocked = self.root / "nonexecutable"
        self.blocked.write_bytes(b"not executable")
        self.blocked.chmod(0o600)
        self.directory = self.root / "directory"
        self.directory.mkdir()
        self.socket = self.root / "socket"
        self.pdf = self.root / "private-name.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\n")

    def test_accepts_only_absolute_executable_regular_files(self):
        from file_launcher import require_executable_path
        self.assertEqual(require_executable_path(self.executable), str(self.executable))
        self.assertEqual(require_executable_path(str(self.executable)), str(self.executable))
        self.assertEqual(require_executable_path(self.alias, allow_symlink=True),
                         str(self.alias))

    def test_rejects_relative_missing_symlink_directory_and_special_paths(self):
        import socket
        from file_launcher import require_executable_path
        dangling = self.root / "dangling"
        dangling.symlink_to(self.root / "missing")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.bind(str(self.socket))
            for candidate in (None, 7, "relative-program", "", "/not-installed/program",
                              self.blocked, self.directory, self.alias, dangling,
                              self.socket, str(self.executable) + "\x00extra"):
                with self.subTest(rejected=repr(candidate)):
                    with self.assertRaisesRegex(RuntimeError,
                                                "^The required executable is missing or unsafe") as raised:
                        require_executable_path(candidate)
                    self.assertNotIn(str(self.root), str(raised.exception))

    def test_native_helpers_fail_before_any_process_or_config_mutation(self):
        with patch("file_launcher.PDF_TARGET_VERIFIER", self.blocked), \
                patch("file_launcher.NATIVE_LAUNCHER", self.blocked), \
                patch("file_launcher.DEFAULT_BROWSER_RESOLVER", self.blocked), \
                patch("file_launcher.subprocess.run") as start, \
                patch("file_launcher.sys.platform", "darwin"):
            from file_launcher import (verify_launch_target, verify_local_file_available,
                                      launch_clean_file, _resolve_default_browser)
            for callback in (
                lambda: verify_launch_target(self.pdf, target_app="com.apple.Preview"),
                lambda: verify_local_file_available(self.pdf),
                lambda: launch_clean_file(self.pdf, target_app="com.apple.Preview"),
                _resolve_default_browser,
            ):
                with self.subTest(callback=repr(callback)):
                    with self.assertRaises(RuntimeError):
                        callback()
            start.assert_not_called()
        self.assertEqual(self.pdf.read_bytes(), b"%PDF-1.4\n")

    def test_validated_helpers_keep_literal_argv_and_customized_destination(self):
        from file_launcher import launch_clean_file, verify_launch_target
        with patch("file_launcher.PDF_TARGET_VERIFIER", self.executable), \
                patch("file_launcher.NATIVE_LAUNCHER", self.executable), \
                patch("file_launcher.subprocess.run",
                      return_value=subprocess.CompletedProcess([], 0)) as run:
            verify_launch_target(self.pdf, target_app="com.apple.Preview")
            launch_clean_file(self.pdf, target_app="com.apple.Preview")
        self.assertEqual(run.call_args_list[0].args[0],
                         [str(self.executable), "com.apple.Preview"])
        self.assertEqual(run.call_args_list[1].args[0],
                         [str(self.executable), "--bundle-id", "com.apple.Preview",
                          str(self.pdf)])
        self.assertEqual(self.pdf.read_bytes(), b"%PDF-1.4\n")

if __name__ == "__main__":
    unittest.main()
