#!/usr/bin/env python3
"""opener-0858: prove the actual sanitizer cannot use the network."""
import os
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

import maximum_network_isolation as isolation
import maximum_sanitizer_memory_launcher as launcher
import maximum_sanitizer_process as sanitizer

ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/var/empty",
    "LANG": "C",
    "PYTHONDONTWRITEBYTECODE": "1",
}


def run_script(source, *args):
    return sanitizer.run_limited_converter(
        (sys.executable, "-I", "-B", "-c", source, *args), b"fixture",
        timeout_seconds=15, max_output_bytes=128, environment=ENV.copy(),
    )


class SanitizerNetworkTests(unittest.TestCase):
    def test_macos_requires_fixed_seatbelt_network_deny_command(self):
        command = ("/usr/bin/python3", "-c", "pass")
        with patch.object(sanitizer.sys, "platform", "darwin"), \
                patch.object(sanitizer.os.path, "isfile", return_value=True), \
                patch.object(sanitizer.os, "access", return_value=True):
            self.assertEqual(
                sanitizer._memory_limited_command(command),
                (isolation.SANDBOX_EXEC, "-p", isolation.NETWORK_DENY_PROFILE, *command),
            )
        self.assertIn("(deny network*)", isolation.NETWORK_DENY_PROFILE)
        self.assertNotIn("allow network", isolation.NETWORK_DENY_PROFILE)

    def test_macos_missing_sandbox_fails_before_child_launch(self):
        with patch.object(sanitizer.sys, "platform", "darwin"), \
                patch.object(sanitizer.os.path, "isfile",
                             side_effect=lambda path: path == "/bin/ps"), \
                patch.object(sanitizer.os, "access", return_value=True), \
                patch.object(sanitizer.subprocess, "Popen") as spawn:
            with self.assertRaises(sanitizer.SanitizerProcessExecutionError) as failure:
                run_script("pass")
            self.assertEqual(str(failure.exception), sanitizer.BLOCK_MESSAGE)
            spawn.assert_not_called()

    def test_linux_filter_is_installed_before_exec(self):
        with patch.object(launcher.sys, "platform", "linux"), \
                patch.object(launcher.sys, "argv", ["launcher", "--", "/usr/bin/true"]), \
                patch.object(launcher, "tighten_address_space_limit", return_value=True), \
                patch.object(isolation, "apply_linux_network_denial") as network, \
                patch.object(launcher.os, "execvpe", side_effect=OSError) as execve:
            self.assertEqual(launcher.main(), launcher.EXEC_FAILED_EXIT_CODE)
            network.assert_called_once()
            execve.assert_called_once()

    def test_linux_filter_failure_never_executes_converter(self):
        with patch.object(launcher.sys, "platform", "linux"), \
                patch.object(launcher.sys, "argv", ["launcher", "--", "/usr/bin/true"]), \
                patch.object(launcher, "tighten_address_space_limit", return_value=True), \
                patch.object(isolation, "apply_linux_network_denial",
                             side_effect=isolation.MaximumNetworkIsolationError("private")), \
                patch.object(launcher.os, "execvpe") as execve:
            self.assertEqual(launcher.main(), launcher.NETWORK_DENIAL_SETUP_FAILED_EXIT_CODE)
            execve.assert_not_called()
        self.assertEqual(launcher.NETWORK_DENIAL_SETUP_FAILED_EXIT_CODE,
                         sanitizer.NETWORK_DENIAL_SETUP_FAILED_EXIT_CODE)

    @unittest.skipUnless(sys.platform in ("linux", "darwin"), "Requires kernel sandbox")
    def test_offline_pdf_processing_remains_available(self):
        result = run_script(
            "import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write(b'offline-ok')"
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"offline-ok")

    @unittest.skipUnless(sys.platform in ("linux", "darwin"), "Requires kernel sandbox")
    def test_real_outbound_connection_to_live_loopback_server_is_denied(self):
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen(2)
            port = str(server.getsockname()[1])
            # A working listener is reachable by the unrestricted test parent.
            with socket.create_connection(("127.0.0.1", int(port)), timeout=2):
                pass
            script = (
                "import socket,sys\n"
                "sys.stdin.buffer.read()\n"
                "try:\n"
                " s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)\n"
                " s.settimeout(1)\n"
                " s.connect(('127.0.0.1',int(sys.argv[1])))\n"
                "except OSError:\n"
                " sys.stdout.buffer.write(b'blocked')\n"
                "else:\n"
                " sys.stdout.buffer.write(b'NETWORK_ALLOWED')\n"
            )
            result = run_script(script, port)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"blocked")

    @unittest.skipUnless(sys.platform in ("linux", "darwin"), "Requires kernel sandbox")
    def test_real_inbound_loopback_listener_is_denied(self):
        script = (
            "import socket,sys\n"
            "sys.stdin.buffer.read()\n"
            "try:\n"
            " s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)\n"
            " s.bind(('127.0.0.1',0))\n"
            " s.listen(1)\n"
            "except OSError:\n"
            " sys.stdout.buffer.write(b'blocked')\n"
            "else:\n"
            " sys.stdout.buffer.write(b'NETWORK_ALLOWED')\n"
        )
        result = run_script(script)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"blocked")

    def test_ci_runs_on_linux_and_macos(self):
        root = Path(__file__).resolve().parents[2]
        workflow = (root / ".github/workflows/consolidated-checks.yml").read_text()
        portable, native = workflow.split("  macos-native-tests:", 1)
        cmd = "tests/maximum/sanitizer-network-denial.py -v"
        self.assertIn("runs-on: ubuntu-latest", portable)
        self.assertIn(cmd, portable)
        self.assertIn("runs-on: macos-latest", native)
        self.assertIn(cmd, native)
        scanner = (root / "scan-and-open.py").read_text()
        self.assertNotIn("maximum_sanitizer_process", scanner)


if __name__ == "__main__":
    unittest.main()
