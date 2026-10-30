#!/usr/bin/env python3
"""Fail-closed Maximum network-denied worker regressions (opener-0308)."""

from dataclasses import FrozenInstanceError
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch, Mock

import maximum_network_isolation as isolation


class OfflineWorkerContractTests(unittest.TestCase):
    def test_network_denied_for_both_directions_with_no_bypass_in_profile(self):
        self.assertIn("(deny network*)", isolation.NETWORK_DENY_PROFILE)
        self.assertIn("(allow default)", isolation.NETWORK_DENY_PROFILE)
        self.assertNotIn("allow network", isolation.NETWORK_DENY_PROFILE)
        self.assertEqual(isolation.SANDBOX_EXEC, "/usr/bin/sandbox-exec")

    def test_uses_fixed_profile_without_shell_or_inherited_network_environment(self):
        success = subprocess.CompletedProcess([], 0)
        with patch.object(isolation.sys, "platform", "darwin"), \
                patch.object(isolation.os.path, "isfile", return_value=True), \
                patch.object(isolation.os, "access", return_value=True), \
                patch.object(isolation.subprocess, "run", return_value=success) as run:
            result = isolation.run_maximum_offline_worker(("/usr/bin/python3", "-c", "pass"),
                                                          timeout_seconds=10)
        self.assertTrue(result.network_denied)
        self.assertFalse(result.authorizes_open)
        self.assertEqual(run.call_count, 1)
        args, kwargs = run.call_args
        self.assertEqual(args[0], [isolation.SANDBOX_EXEC, "-p",
                                   isolation.NETWORK_DENY_PROFILE,
                                   "/usr/bin/python3", "-c", "pass"])
        self.assertNotIn("shell", kwargs)
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertIs(kwargs["stdout"], subprocess.DEVNULL)
        self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
        self.assertIs(kwargs["check"], False)
        self.assertIs(kwargs["close_fds"], True)
        self.assertEqual(kwargs["cwd"], "/")
        self.assertEqual(kwargs["timeout"], 10)
        self.assertEqual(kwargs["env"], isolation.WORKER_ENV)
        self.assertNotIn("HTTP_PROXY", kwargs["env"])
        self.assertNotIn("HOME_SECRET", kwargs["env"])

    def test_unavailable_or_incompatible_platform_never_launches_unsandboxed(self):
        for platform, binary, executable in (("linux", True, True),
                                             ("darwin", False, True),
                                             ("darwin", True, False)):
            with self.subTest(platform=platform, binary=binary, executable=executable), \
                    patch.object(isolation.sys, "platform", platform), \
                    patch.object(isolation.os.path, "isfile", return_value=binary), \
                    patch.object(isolation.os, "access", return_value=executable), \
                    patch.object(isolation.subprocess, "run") as run:
                with self.assertRaises(isolation.MaximumNetworkIsolationError) as fail:
                    isolation.run_maximum_offline_worker(("/usr/bin/python3",))
                self.assertEqual(str(fail.exception), isolation.BLOCK_MESSAGE)
                run.assert_not_called()

    def test_nonzero_failure_timeouts_and_process_errors_are_not_clean(self):
        scenarios = (subprocess.CompletedProcess([], 1),
                     subprocess.TimeoutExpired(["private-path"], 5),
                     OSError("sensitive pathname"))
        for scenario in scenarios:
            with self.subTest(scenario=type(scenario).__name__), \
                    patch.object(isolation.sys, "platform", "darwin"), \
                    patch.object(isolation.os.path, "isfile", return_value=True), \
                    patch.object(isolation.os, "access", return_value=True), \
                    patch.object(isolation.subprocess, "run", **(
                        {"return_value": scenario} if isinstance(scenario, subprocess.CompletedProcess)
                        else {"side_effect": scenario})) as run:
                with self.assertRaises(isolation.MaximumNetworkIsolationError) as error:
                    isolation.run_maximum_offline_worker(("/usr/bin/python3",))
                self.assertEqual(str(error.exception), isolation.BLOCK_MESSAGE)
                self.assertNotIn("sensitive", str(error.exception))
                run.assert_called_once()

    def test_untrusted_command_and_timeout_values_never_start_process(self):
        invalid = ((), [], ["/usr/bin/python3"], ("python3",), ("/usr/bin/python3", ""),
                   ("/usr/bin/python3", "bad\x00thing"),
                   ("/usr/bin/python3",) * (isolation.MAX_ARGUMENTS + 1),
                   ("/usr/bin/python3", "x" * (isolation.MAX_ARGUMENT_BYTES + 1)))
        with patch.object(isolation.subprocess, "run") as run:
            for command in invalid:
                with self.subTest(command=repr(command)[:40]), self.assertRaises(ValueError):
                    isolation.run_maximum_offline_worker(command)
            for timeout in (0, -1, True, False, 1.5, "5", isolation.MAX_TIMEOUT_SECONDS + 1):
                with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                    isolation.run_maximum_offline_worker(("/usr/bin/python3",),
                                                         timeout_seconds=timeout)
            run.assert_not_called()

    def test_success_cannot_be_used_as_a_clean_pdf_verdict(self):
        instance = isolation.OfflineWorkerCompletion()
        self.assertFalse(instance.authorizes_open)
        with self.assertRaises(FrozenInstanceError):
            instance.authorizes_open = True
        with self.assertRaises(ValueError):
            isolation.OfflineWorkerCompletion(False, False)
        with self.assertRaises(ValueError):
            isolation.OfflineWorkerCompletion(True, True)

    def test_deployed_scanner_updater_and_user_preferences_are_not_reconfigured(self):
        root = Path(__file__).resolve().parents[2]
        scanner_path = root / "scan-and-open.py"
        if scanner_path.exists():
            scanner = scanner_path.read_text(encoding="utf-8")
            self.assertNotIn("maximum_network_isolation", scanner)
            self.assertIn("if not cached_clean(cache_id):", scanner)
        from protection_profiles import ProtectionProfileID, PROTECTION_PROFILES
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)


@unittest.skipUnless(sys.platform == "darwin", "Requires actual macOS Seatbelt enforcement")
class MacOSKernelIsolationTests(unittest.TestCase):
    def test_local_execution_succeeds_when_sandbox_available(self):
        done = isolation.run_maximum_offline_worker((sys.executable, "-c", "pass"))
        self.assertTrue(done.network_denied)
        self.assertFalse(done.authorizes_open)

    def test_real_loopback_connection_is_denied_despite_live_local_listener(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            # Verify the target is reachable outside the sandbox.
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                pass
            script = (
                "import socket,sys\n"
                "sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)\n"
                "try:\n"
                " sock.connect(('127.0.0.1',int(sys.argv[1])))\n"
                "except OSError:\n"
                " sys.exit(0)\n"
                "sys.exit(17)\n"
            )
            isolation.run_maximum_offline_worker((sys.executable, "-c", script, str(port)))

    def test_real_local_listener_creation_is_denied(self):
        script = (
            "import socket,sys\n"
            "try:\n"
            " sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)\n"
            " sock.bind(('127.0.0.1',0))\n"
            " sock.listen(1)\n"
            "except OSError:\n"
            " sys.exit(0)\n"
            "sys.exit(17)\n"
        )
        isolation.run_maximum_offline_worker((sys.executable, "-c", script))


if __name__ == "__main__":
    unittest.main()
