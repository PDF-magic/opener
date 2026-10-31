#!/usr/bin/env python3
"""Scanner-child filesystem restrictions, including real macOS kernel probes."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import scanner_filesystem_sandbox as sandbox


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("scanner_fs_gate", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ScannerFilesystemConfinementTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="opener-scanner-fs-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.database = self.root / "signatures"
        self.database.mkdir()
        self.selected = self.root / "selected file.pdf"
        self.selected.write_bytes(b"allowed\n")
        self.private = self.root / "unselected secret.pdf"
        self.private.write_bytes(b"private\n")

    def command(self, scanner="/bin/bash", target=None):
        return [
            scanner, "--database=" + str(self.database), "--recursive",
            "--follow-file-symlinks=2", "--follow-dir-symlinks=2",
            "--alert-exceeds-max=yes", "--alert-encrypted=yes",
            "--max-filesize=0", "--max-scansize=0",
            "--max-scantime=0", "--no-summary", "--",
            str(target or self.selected),
        ]

    def test_policy_restricts_reads_and_writes_without_user_home_exceptions(self):
        profile = sandbox.PROFILE
        self.assertIn("(deny default)", profile)
        self.assertIn('(literal (param "TARGET"))', profile)
        self.assertIn('(subpath (param "BUNDLE"))', profile)
        self.assertIn('(subpath (param "DATABASE"))', profile)
        self.assertIn('(subpath (param "SCRATCH"))', profile)
        self.assertIn('(allow file-write* (subpath (param "SCRATCH")))', profile)
        for broad in ('(allow default)', '(subpath "/Users")',
                      '(subpath "/private")', '(subpath "/")',
                      '(allow network', '(allow process-fork'):
            self.assertNotIn(broad, profile.replace(
                '(allow file-read-metadata (subpath "/"))', ''))

    def test_linux_scans_and_version_checks_preserve_original_argv(self):
        with patch.object(sandbox.sys, "platform", "linux"):
            for command, scanning in ((self.command(), True),
                                      (["/bin/bash", "--version"], False)):
                with sandbox.confined_scanner(command, scan=scanning) as (args, options):
                    self.assertIs(args, command)
                    self.assertEqual(options, {})

    def test_missing_sandbox_fails_closed_before_any_child_launch(self):
        with patch.object(sandbox.sys, "platform", "darwin"), \
                patch.object(sandbox, "SANDBOX_EXEC", "/nonexistent/sandbox-exec"), \
                patch.object(gate.subprocess, "run") as run, \
                patch.object(gate.subprocess, "check_output") as version:
            with self.assertRaisesRegex(sandbox.ScannerFilesystemSandboxError,
                                        "Scanner filesystem isolation"):
                gate.run_scan_command(self.command(), 10)
            self.assertIsNone(gate.scan_engine_version("/bin/bash"))
            run.assert_not_called()
            version.assert_not_called()

    def test_sandbox_paths_are_exact_and_do_not_follow_target_aliases(self):
        alias = self.root / "aliased.pdf"
        alias.symlink_to(self.selected)
        with self.assertRaises(sandbox.ScannerFilesystemSandboxError):
            sandbox._scan_paths(self.command(target=alias), True)
        with self.assertRaises(sandbox.ScannerFilesystemSandboxError):
            sandbox._scan_paths(self.command(target=self.private.parent), True)
        with self.assertRaises(sandbox.ScannerFilesystemSandboxError):
            sandbox._scan_paths(["/bin/bash", "--version", "/tmp/unselected"], False)

    def test_mac_launch_uses_bounded_private_workspace_and_literal_args(self):
        with patch.object(sandbox.sys, "platform", "darwin"):
            if not Path(sandbox.SANDBOX_EXEC).is_file():
                # The policy builder can be inspected on Linux with a mocked
                # platform and helper; execution is tested on macOS below.
                executable = patch.object(sandbox, "_executable", return_value=True)
            else:
                executable = patch.object(sandbox, "_executable", wraps=sandbox._executable)
            with executable:
                with sandbox.confined_scanner(self.command(), scan=True) as (args, options):
                    self.assertEqual(args[0], sandbox.SANDBOX_EXEC)
                    self.assertEqual(args[2], sandbox.PROFILE)
                    self.assertEqual(args[-len(self.command()):], self.command())
                    self.assertIn("TARGET=" + str(self.selected), args)
                    self.assertIn("DATABASE=" + str(self.database), args)
                    self.assertEqual(options["cwd"], "/")
                    self.assertTrue(options["close_fds"])
                    self.assertEqual(options["env"]["HOME"], "/var/empty")
                    self.assertNotIn("PYTHONPATH", options["env"])
                    scratch = Path(options["env"]["TMPDIR"])
                    self.assertTrue(scratch.is_dir())
                    self.assertEqual(scratch.stat().st_mode & 0o077, 0)
                self.assertFalse(scratch.exists(), "Temporary extraction files must be cleaned up")

    @unittest.skipUnless(sys.platform == "darwin", "requires real macOS Seatbelt")
    def test_kernel_denies_other_documents_and_writes_outside_scratch(self):
        # Only our temporary fixture is accessed. Exercise the production
        # command prefix and launch options, not a mock policy interpreter.
        cmd = self.command()
        with sandbox.confined_scanner(cmd, scan=True) as (args, options):
            prefix = args[:-len(cmd)]
            def probe(script, value):
                return subprocess.run(
                    [*prefix, "/bin/bash", "-c", script, "probe", str(value)],
                    capture_output=True, text=True, timeout=15, **options)
            allowed = probe('IFS= read -r line < "$1"; [ "$line" = "allowed" ]',
                            self.selected)
            self.assertEqual(allowed.returncode, 0, allowed.stderr[-300:])
            denied = probe('IFS= read -r line < "$1"', self.private)
            self.assertNotEqual(denied.returncode, 0, "Adjacent document read escaped")
            output = self.root / "outside-scratch"
            denied_write = probe('printf "bad" > "$1"', output)
            self.assertNotEqual(denied_write.returncode, 0, "Outside write escaped")
            self.assertFalse(output.exists())
            allowed_scratch = Path(options["env"]["TMPDIR"]) / "extracted"
            self.assertEqual(probe('printf "ok" > "$1"', allowed_scratch).returncode, 0)
            self.assertEqual(allowed_scratch.read_text(), "ok")
        self.assertEqual(self.private.read_bytes(), b"private\n")


if __name__ == "__main__":
    unittest.main()
