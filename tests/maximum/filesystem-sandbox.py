#!/usr/bin/env python3
"""Real macOS Seatbelt deny tests plus fail-closed contract regressions."""

from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import maximum_filesystem_sandbox as sandbox


class MaximumFilesystemSandboxTests(unittest.TestCase):
    def test_deny_by_default_policy_and_no_broad_filesystem_access(self):
        profile = sandbox.SANDBOX_PROFILE
        self.assertIn("(deny default)", profile)
        self.assertIn('(param "WORKER")', profile)
        self.assertNotIn("(allow default)", profile)
        self.assertNotIn("(allow file-write", profile)
        self.assertNotIn("(allow network", profile)
        self.assertNotIn("(allow process-fork", profile)
        self.assertNotIn('(subpath "/Users")', profile)
        self.assertNotIn('(subpath "/private/tmp")', profile)
        self.assertNotIn('(subpath "/private/var")', profile)
        self.assertNotIn('(subpath "/")', profile.replace('(allow file-read-metadata (subpath "/"))', ''))

    def test_untrusted_request_never_runs_unsandboxed(self):
        for arguments, body, timeout in (
            ([], b"%PDF-1.4\n", 5),
            (("probe",), "not bytes", 5),
            (("probe",), b"", 5),
            (("probe",), b"%PDF" * (sandbox.MAX_INPUT_BYTES // 4 + 1), 5),
            (("probe",), b"valid", 0),
            (("probe",), b"valid", 601),
        ):
            with self.subTest(arguments=str(arguments), body_type=str(type(body)), timeout=timeout):
                with patch.object(sandbox.subprocess, "run") as run:
                    with self.assertRaises(sandbox.MaximumFilesystemSandboxError):
                        sandbox.run_maximum_filesystem_confined_worker(
                            "/bin/bash", arguments, body, timeout_seconds=timeout
                        )
                    run.assert_not_called()

    def test_unsupported_platform_and_missing_sandbox_fail_closed(self):
        with patch.object(sandbox.sys, "platform", "linux"):
            with patch.object(sandbox.subprocess, "run") as run:
                with self.assertRaises(sandbox.MaximumFilesystemSandboxError):
                    sandbox.run_maximum_filesystem_confined_worker(
                        "/bin/bash", ("-c", ":"), b"safe input"
                    )
                run.assert_not_called()
        with patch.object(sandbox, "SANDBOX_EXEC", "/definitely-missing/sandbox-exec"):
            with patch.object(sandbox.subprocess, "run") as run:
                with self.assertRaises(sandbox.MaximumFilesystemSandboxError):
                    sandbox.run_maximum_filesystem_confined_worker(
                        "/bin/bash", ("-c", ":"), b"safe input"
                    )
                run.assert_not_called()

    def test_rejects_symlink_and_nonexecutables(self):
        with tempfile.TemporaryDirectory() as directory:
            link = Path(directory) / "worker"
            link.symlink_to("/bin/bash")
            self.assertFalse(sandbox._trusted_executable(str(link)))
            plain = Path(directory) / "plain"
            plain.write_bytes(b"not a program")
            self.assertFalse(sandbox._trusted_executable(str(plain)))
            self.assertFalse(sandbox._trusted_executable("/bin/../bin/bash"))

    def test_result_is_non_authorizing_and_immutable(self):
        result = sandbox.MaximumFilesystemWorkerExit(0)
        self.assertFalse(result.permits_open)
        with self.assertRaises(FrozenInstanceError):
            result.return_code = 1
        with self.assertRaises(ValueError):
            sandbox.MaximumFilesystemWorkerExit(0, permits_open=True)

    def test_active_scanner_remains_unaffected(self):
        root = Path(__file__).resolve().parents[2]
        scan_gate = (root / "scan-and-open.py").read_text()
        native = (root / "brave-pdf-opener.swift").read_text()
        self.assertNotIn("maximum_filesystem_sandbox", scan_gate)
        self.assertNotIn("maximum_filesystem_sandbox", native)
        self.assertIn("if not cached_clean(cache_id):", scan_gate)
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)

    @unittest.skipUnless(sys.platform == "darwin", "Kernel sandbox probes require macOS")
    def test_real_kernel_denies_filesystem_reads_and_writes(self):
        # All probes use the same production launch boundary and shell builtins,
        # not a mock of sandbox-exec. Nonzero denied operations are expected.
        with tempfile.TemporaryDirectory(prefix="opener-maxfs-") as directory:
            root = Path(directory)
            private = root / "private input.pdf"
            private.write_bytes(b"private marker")
            written = root / "should-not-exist"
            def execute(script, *arguments):
                return sandbox.run_maximum_filesystem_confined_worker(
                    "/bin/bash", ("-c", script, "probe", *map(str, arguments)),
                    b"harmless stdin\n", timeout_seconds=15,
                )
            permitted = execute('IFS= read -r line; [ "$line" = "harmless stdin" ]')
            if permitted.return_code != 0:
                # Diagnostic is confined to this fixed harmless fixture; never
                # run diagnostics on a user PDF or echo arbitrary worker stderr.
                probe = sandbox.subprocess.run(
                    [sandbox.SANDBOX_EXEC, "-p", sandbox.SANDBOX_PROFILE,
                     "-D", "WORKER=/bin/bash", "/bin/bash", "-c",
                     'IFS= read -r line; [ "$line" = "harmless stdin" ]'],
                    input=b"harmless stdin\\n", capture_output=True, timeout=10,
                    cwd="/", env={"PATH": "/usr/bin:/bin", "HOME": "/var/empty", "LC_ALL": "C"},
                )
                self.fail("Confined stdin probe failed: %s; benign diagnostics: %s" % (
                    probe.returncode, probe.stderr.decode("utf-8", errors="replace")[-300:]))
            self.assertEqual(permitted.return_code, 0,
                             "The sandbox must permit an in-memory worker to run")
            denied_read = execute('IFS= read -r line < "$1"', private)
            self.assertNotEqual(denied_read.return_code, 0,
                                "The kernel must deny private document path reads")
            denied_write = execute('printf "blocked" > "$1"', written)
            self.assertNotEqual(denied_write.return_code, 0,
                                "The kernel must deny filesystem writes")
            self.assertFalse(written.exists())
            alias = root / "alias.pdf"
            alias.symlink_to(private)
            self.assertNotEqual(execute('IFS= read -r line < "$1"', alias).return_code, 0,
                                "Symlinks must not bypass filesystem confinement")
            self.assertEqual(private.read_bytes(), b"private marker")

    @unittest.skipUnless(sys.platform == "darwin", "macOS process launch only")
    def test_environment_is_minimal_and_sandbox_is_mandatory(self):
        with patch.object(sandbox.subprocess, "run") as run:
            run.return_value.returncode = 0
            outcome = sandbox.run_maximum_filesystem_confined_worker(
                "/bin/bash", ("-c", ":"), b"safe input", timeout_seconds=5,
            )
            call = run.call_args
            self.assertEqual(call.args[0][0], "/usr/bin/sandbox-exec")
            self.assertIn("(deny default)", call.args[0][2])
            self.assertIn("WORKER=/bin/bash", call.args[0])
            self.assertEqual(call.kwargs["cwd"], "/")
            self.assertTrue(call.kwargs["close_fds"])
            self.assertNotIn("PYTHONPATH", call.kwargs["env"])
            self.assertEqual(call.kwargs["env"]["HOME"], "/var/empty")
            self.assertFalse(outcome.permits_open)


if __name__ == "__main__":
    unittest.main()
