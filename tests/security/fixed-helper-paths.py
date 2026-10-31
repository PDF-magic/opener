#!/usr/bin/env python3
"""opener-0849: trusted helpers must never be resolved from PATH or cwd."""

from contextlib import ExitStack
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
import file_launcher
import maximum_process_termination as worker
import maximum_sanitizer_process as sanitizer

spec = importlib.util.spec_from_file_location("fixed_helper_scanner_gate", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class FixedHelperPathsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="opener-0849-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        # An executable with the expected basename in PATH is not trusted.
        self.spoof = self.root / "trusted-helper"
        self.spoof.write_bytes(b"#!/bin/sh\nexit 99\n")
        self.spoof.chmod(0o700)

    def test_helper_supervisors_reject_path_search_and_relative_executables(self):
        invalid = (
            "trusted-helper", "./trusted-helper", "../trusted-helper",
            "other/trusted-helper", "/usr/bin/../bin/trusted-helper",
        )
        for executable in invalid:
            with self.subTest(executable=executable):
                command = (executable, "--version")
                with patch.dict(os.environ, {"PATH": str(self.root)}), \
                        patch.object(worker.subprocess, "Popen") as spawn:
                    with self.assertRaises(worker.MaximumProcessTerminationError) as failure:
                        worker.run_limited_worker(
                            command, b"%PDF", timeout_seconds=1,
                            environment={"PATH": str(self.root)},
                        )
                    self.assertEqual(str(failure.exception), worker.BLOCK_MESSAGE)
                    spawn.assert_not_called()
                with patch.dict(os.environ, {"PATH": str(self.root)}), \
                        patch.object(sanitizer, "_memory_limited_command") as limit, \
                        patch.object(sanitizer.subprocess, "Popen") as spawn:
                    with self.assertRaises(sanitizer.SanitizerProcessExecutionError) as failure:
                        sanitizer.run_limited_converter(
                            command, b"%PDF", timeout_seconds=1, max_output_bytes=1024,
                            environment={"PATH": str(self.root)},
                        )
                    self.assertEqual(str(failure.exception), sanitizer.BLOCK_MESSAGE)
                    limit.assert_not_called()
                    spawn.assert_not_called()
        self.assertEqual(self.spoof.read_bytes(), b"#!/bin/sh\nexit 99\n")

    def test_absolute_executable_does_not_depend_on_path_for_process_supervisors(self):
        command = (str(self.spoof), "--version")
        self.assertTrue(os.path.isabs(command[0]))
        with patch.dict(os.environ, {"PATH": "/nonexistent"}), \
                patch.object(worker.subprocess, "Popen", side_effect=OSError("blocked")) as spawn:
            with self.assertRaises(worker.MaximumProcessTerminationError):
                worker.run_limited_worker(
                    command, b"%PDF", timeout_seconds=1,
                    environment={"PATH": "/nonexistent"},
                )
            self.assertEqual(spawn.call_args.args[0], command)
        with patch.dict(os.environ, {"PATH": "/nonexistent"}), \
                patch.object(sanitizer, "_memory_limited_command", return_value=command) as limit, \
                patch.object(sanitizer.subprocess, "Popen", side_effect=OSError("blocked")) as spawn:
            with self.assertRaises(sanitizer.SanitizerProcessExecutionError):
                sanitizer.run_limited_converter(
                    command, b"%PDF", timeout_seconds=1, max_output_bytes=1024,
                    environment={"PATH": "/nonexistent"},
                )
            limit.assert_called_once_with(command)
            self.assertEqual(spawn.call_args.args[0], command)

    def test_clamav_discovery_ignores_spoofed_path_entries(self):
        fake_scanner = self.root / "clamscan"
        fake_scanner.write_bytes(b"#!/bin/sh\nexit 99\n")
        fake_scanner.chmod(0o700)
        self.assertTrue(all(
            os.path.isabs(candidate) and
            os.path.normpath(candidate) == candidate
            for candidate in gate.CLAMAV_CANDIDATES
        ))
        with patch.dict(os.environ, {"PATH": str(self.root)}):
            discovered = gate.detect_clamav_installation()
        self.assertTrue(discovered is None or discovered in gate.CLAMAV_CANDIDATES)
        self.assertNotEqual(discovered, str(fake_scanner))

    def test_native_helpers_use_installed_module_sibling_paths_not_path(self):
        module_root = Path(file_launcher.__file__).resolve().parent
        paths = {
            "launch-scanned-file": file_launcher.NATIVE_LAUNCHER,
            "verify-pdf-target": file_launcher.PDF_TARGET_VERIFIER,
            "resolve-default-browser": file_launcher.DEFAULT_BROWSER_RESOLVER,
        }
        for name, actual in paths.items():
            with self.subTest(helper=name):
                self.assertEqual(actual, module_root / name)
                self.assertTrue(actual.is_absolute())
                self.assertNotEqual(actual, self.root / name)
        selected = self.root / "selection.pdf"
        selected.write_bytes(b"%PDF-1.4\n")
        with patch.dict(os.environ, {"PATH": str(self.root)}), \
                patch.object(file_launcher, "require_executable_path") as validate, \
                patch.object(file_launcher.subprocess, "run") as run:
            file_launcher.launch_clean_file(selected, target_app="com.brave.Browser")
            validate.assert_called_once_with(file_launcher.NATIVE_LAUNCHER)
            self.assertEqual(
                run.call_args.args[0],
                [str(file_launcher.NATIVE_LAUNCHER), "--bundle-id",
                 "com.brave.Browser", str(selected)],
            )
            run.reset_mock()
            run.return_value = subprocess.CompletedProcess([], 0, b"", b"")
            file_launcher.verify_launch_target(selected, target_app="com.brave.Browser")
            validate.assert_any_call(file_launcher.PDF_TARGET_VERIFIER,
                                     file_launcher.PDF_TARGET_VERIFICATION_MESSAGE)
            self.assertEqual(
                run.call_args.args[0],
                [str(file_launcher.PDF_TARGET_VERIFIER), "com.brave.Browser"],
            )
            run.reset_mock()
            run.return_value = subprocess.CompletedProcess([], 0, b"com.brave.Browser\n", b"")
            self.assertEqual(file_launcher._resolve_default_browser(), "com.brave.Browser")
            validate.assert_any_call(file_launcher.DEFAULT_BROWSER_RESOLVER,
                                     file_launcher.PDF_DEFAULT_BROWSER_UNAVAILABLE_MESSAGE)
            self.assertEqual(run.call_args.args[0], [str(file_launcher.DEFAULT_BROWSER_RESOLVER)])
        self.assertEqual(selected.read_bytes(), b"%PDF-1.4\n")

    def test_finder_shell_wrapper_uses_fixed_system_interpreter(self):
        source = (ROOT / "allow-and-open.sh").read_text(encoding="utf-8")
        self.assertIn('/usr/bin/python3 "$script_dir/record-scan-origin.py" "$@"', source)
        self.assertIn('exec /usr/bin/python3 "$script_dir/scan-and-open.py" "$@"', source)
        self.assertNotIn("env python3", source)
        self.assertNotIn("exec python3 ", source)


if __name__ == "__main__":
    unittest.main()
