#!/usr/bin/env python3
"""opener-0491: bound memory use in the optional Maximum sanitizer process."""
import errno
import os
import resource
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import maximum_sanitizer_memory_launcher as launcher
import maximum_sanitizer_process as sanitizer


ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/var/empty",
    "LANG": "C",
    "PYTHONDONTWRITEBYTECODE": "1",
}


def run_script(source, *, timeout=3, contents=b"input"):
    return sanitizer.run_limited_converter(
        (sys.executable, "-I", "-B", "-c", source),
        contents,
        timeout_seconds=timeout,
        max_output_bytes=128,
        environment=ENV.copy(),
    )


class SanitizerMemoryLimitTests(unittest.TestCase):
    def test_memory_ceiling_is_fixed_and_not_document_or_preference_controlled(self):
        self.assertEqual(sanitizer.MAX_SANITIZER_MEMORY_BYTES, 1024 * 1024 * 1024)
        self.assertEqual(launcher.MEMORY_LIMIT_SETUP_FAILED_EXIT_CODE,
                         sanitizer.MEMORY_LIMIT_SETUP_FAILED_EXIT_CODE)

    def test_tightening_never_relaxes_an_existing_address_space_limit(self):
        state = [512 * 1024 * 1024, 512 * 1024 * 1024]

        def getlimit(_kind):
            return tuple(state)

        def setlimit(_kind, value):
            state[:] = value

        with patch.object(launcher.sys, "platform", "linux"), \
                patch.object(launcher.resource, "getrlimit", side_effect=getlimit), \
                patch.object(launcher.resource, "setrlimit", side_effect=setlimit):
            self.assertTrue(launcher.tighten_address_space_limit(
                sanitizer.MAX_SANITIZER_MEMORY_BYTES))
        self.assertEqual(state, [512 * 1024 * 1024, 512 * 1024 * 1024])

    def test_unavailable_address_space_limit_fails_closed(self):
        with patch.object(launcher.sys, "platform", "linux"), \
                patch.object(launcher.resource, "getrlimit",
                             return_value=(resource.RLIM_INFINITY, resource.RLIM_INFINITY)), \
                patch.object(launcher.resource, "setrlimit", side_effect=OSError("private")):
            self.assertFalse(launcher.tighten_address_space_limit(
                sanitizer.MAX_SANITIZER_MEMORY_BYTES))

    @unittest.skipUnless(sys.platform == "linux", "Linux hard RLIMIT_AS validation")
    def test_real_converter_cannot_allocate_past_hard_address_space_ceiling(self):
        script = f"""
import sys
sys.stdin.buffer.read()
try:
    bytearray({sanitizer.MAX_SANITIZER_MEMORY_BYTES * 2})
except MemoryError:
    print('memory-ceiling-enforced')
    raise SystemExit(0)
raise SystemExit(3)
"""
        result = run_script(script, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"memory-ceiling-enforced\n")

    def test_actual_process_group_memory_is_measured(self):
        result = run_script(
            "import sys,time; sys.stdin.buffer.read(); time.sleep(.15); "
            "sys.stdout.write('ok'); sys.stdout.flush()"
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"ok")

    def test_exit_status_observation_does_not_reap_group_leader(self):
        process = subprocess.Popen(
            (sys.executable, "-I", "-B", "-c", "pass"),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
            cwd="/",
            env=ENV.copy(),
        )
        try:
            deadline = time.monotonic() + 3
            exited = False
            while not exited and time.monotonic() < deadline:
                exited = sanitizer._process_has_exited_without_reaping(process)
                if not exited:
                    time.sleep(0.01)
            self.assertTrue(exited)
            self.assertIsNone(process.returncode)
        finally:
            process.wait(timeout=3)

    def test_macos_process_group_rss_filters_complete_process_table(self):
        table = subprocess.CompletedProcess(
            ("ps",), 0, b"101 101 120\n102 101 80\n103 103 999\n", None,
        )
        with patch.object(sanitizer.subprocess, "run", return_value=table) as probe:
            measured = sanitizer._darwin_process_group_memory_bytes(
                101, allow_empty=False, timeout_seconds=1,
            )
        self.assertEqual(measured, 200 * 1024)
        probe.assert_called_once()
        self.assertEqual(probe.call_args.args[0], ("/bin/ps", "-A", "-o", "pid=,pgid=,rss="))

    def test_macos_missing_group_is_allowed_only_after_exit(self):
        table = subprocess.CompletedProcess(("ps",), 0, b"1 1 100\n", None)
        with patch.object(sanitizer.subprocess, "run", return_value=table):
            with self.assertRaises(sanitizer.SanitizerProcessMemoryLimitError):
                sanitizer._darwin_process_group_memory_bytes(
                    101, allow_empty=False, timeout_seconds=1,
                )
            self.assertEqual(
                sanitizer._darwin_process_group_memory_bytes(
                    101, allow_empty=True, timeout_seconds=1,
                ), 0,
            )

    def test_malformed_macos_process_table_fails_closed(self):
        malformed = subprocess.CompletedProcess(("ps",), 0, b"not a process row\n", None)
        with patch.object(sanitizer.subprocess, "run", return_value=malformed):
            with self.assertRaises(sanitizer.SanitizerProcessMemoryLimitError):
                sanitizer._darwin_process_group_memory_bytes(
                    101, allow_empty=True, timeout_seconds=1,
                )

    def test_macos_exit_detection_does_not_reap_a_running_process(self):
        process = type("FakeProcess", (), {"pid": 101, "returncode": None})()
        completed = subprocess.CompletedProcess(("ps",), 0, b"S+\n", None)
        with patch.object(sanitizer.sys, "platform", "darwin"), \
                patch.object(sanitizer.subprocess, "run", return_value=completed) as probe:
            self.assertFalse(sanitizer._process_has_exited_without_reaping(process))
        probe.assert_called_once()
        self.assertEqual(
            probe.call_args.args[0], ("/bin/ps", "-o", "stat=", "-p", "101")
        )
        self.assertIsNone(process.returncode)

    def test_macos_exit_detection_recognizes_zombie_without_reaping(self):
        process = type("FakeProcess", (), {"pid": 101, "returncode": None})()
        completed = subprocess.CompletedProcess(("ps",), 0, b"Z+\n", None)
        with patch.object(sanitizer.sys, "platform", "darwin"), \
                patch.object(sanitizer.subprocess, "run", return_value=completed) as probe:
            self.assertTrue(sanitizer._process_has_exited_without_reaping(process))
        probe.assert_called_once()
        self.assertIsNone(process.returncode)

    def test_macos_exit_detection_retries_empty_status_but_requires_zombie(self):
        process = type("FakeProcess", (), {"pid": 101, "returncode": None})()
        empty = subprocess.CompletedProcess(("ps",), 0, b"", None)
        zombie = subprocess.CompletedProcess(("ps",), 0, b"Z+\n", None)
        with patch.object(sanitizer.sys, "platform", "darwin"), \
                patch.object(sanitizer.time, "sleep"), \
                patch.object(sanitizer.subprocess, "run",
                             side_effect=(empty, zombie)) as probe:
            self.assertTrue(sanitizer._process_has_exited_without_reaping(process))
            self.assertEqual(probe.call_count, 2)
        with patch.object(sanitizer.sys, "platform", "darwin"), \
                patch.object(sanitizer.time, "sleep"), \
                patch.object(sanitizer.subprocess, "run",
                             return_value=empty) as probe:
            with self.assertRaises(sanitizer.SanitizerProcessExecutionError):
                sanitizer._process_has_exited_without_reaping(process)
            # Four targeted probes plus the independent process-table check.
            self.assertEqual(probe.call_count, 5)
        self.assertIsNone(process.returncode)

    def test_macos_exit_detection_uses_verified_fallback_snapshot(self):
        process = type("FakeProcess", (), {"pid": 101, "returncode": None})()
        empty = subprocess.CompletedProcess(("ps",), 0, b"", None)
        verified = subprocess.CompletedProcess(
            ("ps",), 0, b"101 101 Z+\n202 202 S+\n", None
        )
        # A verified live leader is not an exit; missing or malformed
        # identity remains an error, never a clean shutdown.
        untrusted = (b"102 101 Z+\n", b"101 202 Z+\n",
                     b"invalid-data\n")
        with patch.object(sanitizer.sys, "platform", "darwin"), \
                patch.object(sanitizer.time, "sleep"), patch.object(
                    sanitizer.subprocess, "run",
                    side_effect=(empty, empty, empty, empty, verified),
                ) as probe:
            self.assertTrue(sanitizer._process_has_exited_without_reaping(process))
            self.assertEqual(probe.call_count, 5)
            self.assertEqual(
                probe.call_args.args[0], ("/bin/ps", "-A", "-o", "pid=,pgid=,stat=")
            )
        for rows in untrusted:
            with self.subTest(rows=rows), \
                    patch.object(sanitizer.sys, "platform", "darwin"), \
                    patch.object(sanitizer.time, "sleep"), patch.object(
                        sanitizer.subprocess, "run",
                        side_effect=(empty, empty, empty, empty,
                                     subprocess.CompletedProcess(("ps",), 0, rows)),
                    ):
                with self.assertRaises(sanitizer.SanitizerProcessExecutionError):
                    sanitizer._process_has_exited_without_reaping(process)
        # The fallback may identify a still-running group leader. This must
        # return False, not treat the process as exited or permit cleanup.
        live = subprocess.CompletedProcess(("ps",), 0, b"101 101 S+\n", None)
        with patch.object(sanitizer.sys, "platform", "darwin"), \
                patch.object(sanitizer.time, "sleep"), patch.object(
                    sanitizer.subprocess, "run",
                    side_effect=(empty, empty, empty, empty, live),
                ) as probe:
            self.assertIs(sanitizer._process_has_exited_without_reaping(process), False)
            self.assertEqual(probe.call_count, 5)
        self.assertIsNone(process.returncode)

    def test_macos_exit_detection_fails_closed_when_status_is_unavailable(self):
        process = type("FakeProcess", (), {"pid": 101, "returncode": None})()
        with patch.object(sanitizer.sys, "platform", "darwin"), \
                patch.object(sanitizer.subprocess, "run",
                             side_effect=OSError("private")) as probe:
            with self.assertRaises(sanitizer.SanitizerProcessExecutionError):
                sanitizer._process_has_exited_without_reaping(process)
        probe.assert_called_once()

    def test_macos_eperm_cleanup_requires_no_live_group_members(self):
        process = type("FakeProcess", (), {"pid": 101, "returncode": None})()
        leader = subprocess.CompletedProcess(("ps",), 0, b"Z+\n", None)
        zombies = subprocess.CompletedProcess(
            ("ps",), 0, b"101 101 Z+\n102 101 Z\n201 201 S+\n", None
        )
        living = subprocess.CompletedProcess(
            ("ps",), 0, b"101 101 Z+\n102 101 S+\n", None
        )
        missing_leader = subprocess.CompletedProcess(
            ("ps",), 0, b"102 101 Z+\n", None
        )
        with patch.object(sanitizer.sys, "platform", "darwin"), \
                patch.object(sanitizer.time, "sleep"), \
                patch.object(sanitizer.os, "killpg",
                             side_effect=PermissionError(errno.EPERM, "denied")), \
                patch.object(process, "kill", return_value=None, create=True) as kill:
            with patch.object(sanitizer.subprocess, "run",
                              side_effect=(leader, zombies)) as probe:
                sanitizer._stop_process_group(process)
                self.assertEqual(probe.call_count, 2)
                kill.assert_not_called()
            for group in (living, missing_leader):
                with self.subTest(group=group.stdout), \
                        patch.object(sanitizer.subprocess, "run",
                                     side_effect=(leader, group) * 4) as probe:
                    with self.assertRaises(sanitizer.SanitizerProcessExecutionError):
                        sanitizer._stop_process_group(process)
                    self.assertEqual(probe.call_count, 8)
                    kill.assert_called()
                    kill.reset_mock()

    def test_memory_overage_kills_the_process_group_and_returns_no_output(self):
        killed = []
        real_killpg = os.killpg

        def kill_group(pid, sig):
            killed.append((pid, sig))
            return real_killpg(pid, sig)

        with patch.object(sanitizer, "_process_group_memory_bytes",
                          return_value=sanitizer.MAX_SANITIZER_MEMORY_BYTES + 1), \
                patch.object(sanitizer.os, "killpg", side_effect=kill_group):
            with self.assertRaises(sanitizer.SanitizerProcessMemoryLimitError) as caught:
                run_script("import time; time.sleep(20)", timeout=2)
        self.assertEqual(str(caught.exception), sanitizer.MEMORY_LIMIT_MESSAGE)
        self.assertTrue(killed)
        self.assertEqual(killed[0][1], signal.SIGKILL)
        self.assertNotEqual(killed[0][0], os.getpgrp())

    def test_unavailable_memory_measurement_fails_closed(self):
        with patch.object(sanitizer, "_process_group_memory_bytes",
                          side_effect=sanitizer.SanitizerProcessMemoryLimitError(
                              sanitizer.MEMORY_LIMIT_MESSAGE)):
            with self.assertRaises(sanitizer.SanitizerProcessMemoryLimitError):
                run_script("import time; time.sleep(20)", timeout=2)

    def test_unsupported_platform_fails_before_launch(self):
        with patch.object(sanitizer.sys, "platform", "freebsd"), \
                patch.object(sanitizer.subprocess, "Popen") as launch:
            with self.assertRaises(sanitizer.SanitizerProcessMemoryLimitError):
                run_script("pass")
        launch.assert_not_called()

    def test_ci_runs_memory_checks_on_ubuntu_and_macos(self):
        from pathlib import Path
        workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/consolidated-checks.yml").read_text()
        portable = workflow.split("  macos-native-tests:", 1)[0]
        native = workflow.split("  macos-native-tests:", 1)[1]
        self.assertIn("runs-on: ubuntu-latest", portable)
        self.assertIn("tests/maximum/sanitizer-memory-limits.py -v", portable)
        self.assertIn("runs-on: macos-latest", native)
        self.assertIn("tests/maximum/sanitizer-memory-limits.py -v", native)


if __name__ == "__main__":
    unittest.main()
