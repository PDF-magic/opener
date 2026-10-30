#!/usr/bin/env python3
"""opener-0490: hard deadlines and process-tree cleanup for PDF sanitization."""
import errno
import os
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import Mock, patch

import maximum_sanitizer_process as sanitizer


ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/var/empty",
    "LANG": "C",
    "PYTHONDONTWRITEBYTECODE": "1",
}


def run_script(source, *, timeout=2, contents=b"input", max_output_bytes=128):
    def invoke():
        return sanitizer.run_limited_converter(
            (sys.executable, "-I", "-B", "-c", source),
            contents,
            timeout_seconds=timeout,
            max_output_bytes=max_output_bytes,
            environment=ENV.copy(),
        )

    # Test-only, bounded errno diagnostics: never log worker output, source
    # content, command arguments, paths, or the sanitizer's internal error.
    # Do not interfere with tests that explicitly spy on process-group kills.
    if sys.platform != "darwin" or isinstance(sanitizer.os.killpg, Mock):
        return invoke()
    real_killpg = sanitizer.os.killpg

    def annotated_killpg(pid, sig):
        try:
            return real_killpg(pid, sig)
        except OSError as error:
            print("macOS sanitizer cleanup errno=" +
                  errno.errorcode.get(error.errno, "UNKNOWN"), file=sys.stderr)
            raise

    with patch.object(sanitizer.os, "killpg", side_effect=annotated_killpg):
        return invoke()


class SanitizerProcessDeadlineTests(unittest.TestCase):
    def test_silent_hung_converter_is_killed_and_reaped_by_deadline(self):
        killed = []
        real_killpg = os.killpg
        def kill_group(pid, sig):
            killed.append((pid, sig))
            return real_killpg(pid, sig)

        start = time.monotonic()
        with patch.object(sanitizer.os, "killpg", side_effect=kill_group):
            with self.assertRaises(sanitizer.SanitizerProcessTimedOut) as caught:
                run_script("import time; time.sleep(20)", timeout=1)
        self.assertLess(time.monotonic() - start, 5)
        self.assertEqual(str(caught.exception), sanitizer.TIMEOUT_MESSAGE)
        self.assertTrue(killed)
        self.assertEqual(killed[0][1], signal.SIGKILL)
        self.assertNotEqual(killed[0][0], os.getpgrp())

    def test_descendant_cannot_keep_stdout_open_after_converter_exits(self):
        killed = []
        real_killpg = os.killpg
        source = (
            "import subprocess,sys; "
            "subprocess.Popen([sys.executable,'-I','-B','-c',"
            "'import time;time.sleep(20)'], stdin=subprocess.DEVNULL, "
            "stderr=subprocess.DEVNULL); "
            "sys.stdin.buffer.read(); sys.stdout.write('parent done'); "
            "sys.stdout.flush()"
        )
        def kill_group(pid, sig):
            killed.append((pid, sig))
            return real_killpg(pid, sig)

        start = time.monotonic()
        with patch.object(sanitizer.os, "killpg", side_effect=kill_group):
            with self.assertRaises(sanitizer.SanitizerProcessTimedOut):
                run_script(source, timeout=1)
        self.assertLess(time.monotonic() - start, 5)
        self.assertTrue(killed)
        self.assertNotEqual(killed[0][0], os.getpgrp())

    def test_success_still_terminates_leftover_descendants(self):
        killed = []
        real_killpg = os.killpg
        source = (
            "import subprocess,sys; "
            "subprocess.Popen([sys.executable,'-I','-B','-c',"
            "'import time;time.sleep(20)'], stdin=subprocess.DEVNULL, "
            "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
            "sys.stdin.buffer.read(); sys.stdout.write('ok'); sys.stdout.flush()"
        )
        def kill_group(pid, sig):
            killed.append((pid, sig))
            return real_killpg(pid, sig)

        with patch.object(sanitizer.os, "killpg", side_effect=kill_group):
            result = run_script(source)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"ok")
        self.assertEqual(len(killed), 1)
        self.assertNotEqual(killed[0][0], os.getpgrp())

    def test_macos_eperm_accepts_only_an_exited_zombie_group(self):
        process = type("Process", (), {"pid": 101, "kill": lambda self: None})()
        table = subprocess.CompletedProcess(
            ("/bin/ps",), 0, b"101 101 Z+\n102 101 Z\n103 103 S\n"
        )
        with patch.object(sanitizer.sys, "platform", "darwin"), \
                patch.object(sanitizer.os, "killpg",
                             side_effect=PermissionError(errno.EPERM, "zombie group")), \
                patch.object(sanitizer, "_process_has_exited_without_reaping",
                             return_value=True) as exited, \
                patch.object(sanitizer.subprocess, "run", return_value=table) as probe:
            sanitizer._stop_process_group(process)
        exited.assert_called_once_with(process)
        self.assertEqual(
            probe.call_args.args[0], ("/bin/ps", "-A", "-o", "pid=,pgid=,stat=")
        )

    def test_macos_eperm_with_live_descendant_fails_closed(self):
        process = type("Process", (), {"pid": 101, "kill": lambda self: None})()
        table = subprocess.CompletedProcess(
            ("/bin/ps",), 0, b"101 101 Z\n102 101 S\n"
        )
        with patch.object(sanitizer.sys, "platform", "darwin"), \
                patch.object(sanitizer.os, "killpg",
                             side_effect=PermissionError(errno.EPERM, "live group")), \
                patch.object(sanitizer, "_process_has_exited_without_reaping",
                             return_value=True), \
                patch.object(sanitizer.subprocess, "run", return_value=table):
            with self.assertRaises(sanitizer.SanitizerProcessExecutionError):
                sanitizer._stop_process_group(process)

    def test_macos_eperm_with_unverified_or_running_leader_fails_closed(self):
        process = type("Process", (), {"pid": 101, "kill": lambda self: None})()
        table = subprocess.CompletedProcess(("/bin/ps",), 0, b"101 101 Z\n")
        with patch.object(sanitizer.sys, "platform", "darwin"), \
                patch.object(sanitizer.os, "killpg",
                             side_effect=PermissionError(errno.EPERM, "unknown")):
            with patch.object(sanitizer, "_process_has_exited_without_reaping",
                              return_value=False), \
                    patch.object(sanitizer.subprocess, "run") as probe:
                with self.assertRaises(sanitizer.SanitizerProcessExecutionError):
                    sanitizer._stop_process_group(process)
                probe.assert_not_called()
            with patch.object(sanitizer, "_process_has_exited_without_reaping",
                              return_value=True), \
                    patch.object(sanitizer.subprocess, "run",
                                 side_effect=subprocess.TimeoutExpired("ps", 0.5)):
                with self.assertRaises(sanitizer.SanitizerProcessExecutionError):
                    sanitizer._stop_process_group(process)
            with patch.object(sanitizer, "_process_has_exited_without_reaping",
                              return_value=True), \
                    patch.object(sanitizer.subprocess, "run", return_value=table):
                sanitizer._stop_process_group(process)

    def test_macos_eperm_needs_verified_zombie_group_leader(self):
        process = type("Process", (), {"pid": 101, "kill": lambda self: None})()
        # A missing leader, malformed output or living descendant is
        # insufficient evidence to accept an EPERM cleanup failure.
        unverified_tables = (
            b"",
            b"202 202 Z\n",
            b"102 101 Z\n",
            b"101 202 Z\n102 101 Z\n",
            b"101 101 S\n",
            b"101 101 Z\n102 101 S\n",
            b"not-a-process-record\n",
        )
        for output in unverified_tables:
            with (
                self.subTest(record=output),
                patch.object(sanitizer.sys, "platform", "darwin"),
                patch.object(sanitizer.os, "killpg",
                             side_effect=PermissionError(errno.EPERM, "unverified")),
                patch.object(sanitizer, "_process_has_exited_without_reaping",
                             return_value=True),
                patch.object(sanitizer.subprocess, "run",
                             return_value=subprocess.CompletedProcess(
                                 ("/bin/ps",), 0, output,
                             )),
            ):
                with self.assertRaises(sanitizer.SanitizerProcessExecutionError):
                    sanitizer._stop_process_group(process)


    def test_non_eperm_cleanup_error_never_uses_zombie_exception(self):
        process = type("Process", (), {"pid": 101, "kill": lambda self: None})()
        with patch.object(sanitizer.sys, "platform", "darwin"), \
                patch.object(sanitizer.os, "killpg",
                             side_effect=OSError(errno.EINVAL, "invalid group")), \
                patch.object(sanitizer, "_darwin_group_has_only_zombies") as check:
            with self.assertRaises(sanitizer.SanitizerProcessExecutionError):
                sanitizer._stop_process_group(process)
            check.assert_not_called()

    def test_macos_transient_status_probe_requires_verified_zombie(self):
        process = type("Process", (), {"pid": 101, "returncode": None})()
        records = (
            subprocess.TimeoutExpired("/bin/ps", 0.5),
            subprocess.CompletedProcess(("/bin/ps",), 0, b"Z+\n"),
        )
        with patch.object(sanitizer.sys, "platform", "darwin"), patch.object(
            sanitizer.subprocess, "run", side_effect=records
        ) as probe:
            self.assertTrue(sanitizer._process_has_exited_without_reaping(process))
            self.assertEqual(probe.call_count, 2)

        with patch.object(sanitizer.sys, "platform", "darwin"), patch.object(
            sanitizer.subprocess, "run", side_effect=[
                subprocess.CalledProcessError(1, "/bin/ps"),
                subprocess.TimeoutExpired("/bin/ps", 0.5),
                subprocess.CalledProcessError(1, "/bin/ps"),
                subprocess.TimeoutExpired("/bin/ps", 0.5),
                subprocess.CompletedProcess(
                    ("/bin/ps",), 0, b"202 202 S+\n",
                ),
            ]
        ) as probe:
            with self.assertRaises(sanitizer.SanitizerProcessExecutionError):
                sanitizer._process_has_exited_without_reaping(process)
            self.assertEqual(probe.call_count, 5)

        # An initially malformed status may be retried only until a trusted
        # kernel snapshot explicitly confirms the worker has exited.
        with patch.object(sanitizer.sys, "platform", "darwin"), patch.object(
            sanitizer.subprocess, "run", side_effect=[
                subprocess.CompletedProcess(("/bin/ps",), 0, b"?\n"),
                subprocess.CompletedProcess(("/bin/ps",), 0, b"Z+\n"),
            ]
        ) as probe:
            self.assertTrue(sanitizer._process_has_exited_without_reaping(process))
            self.assertEqual(probe.call_count, 2)

        # Four inconclusive targeted probes trigger one independent process-
        # table snapshot; even that cannot authorize an unverifiable exit.
        with patch.object(sanitizer.sys, "platform", "darwin"), patch.object(
            sanitizer.subprocess, "run", return_value=(
                subprocess.CompletedProcess(("/bin/ps",), 0, b"?\n")
            )
        ) as probe:
            with self.assertRaises(sanitizer.SanitizerProcessExecutionError):
                sanitizer._process_has_exited_without_reaping(process)
            self.assertEqual(probe.call_count, 5)
            self.assertEqual(
                probe.call_args.args[0], ("/bin/ps", "-A", "-o", "pid=,pgid=,stat="),
            )

        # A live state is never interpreted as a successfully exited worker.
        with patch.object(sanitizer.sys, "platform", "darwin"), patch.object(
            sanitizer.subprocess, "run",
            return_value=subprocess.CompletedProcess(("/bin/ps",), 0, b"S+\n"),
        ):
            self.assertFalse(sanitizer._process_has_exited_without_reaping(process))

    def test_output_limit_is_enforced_while_reading(self):
        source = "import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write(b'X'*129)"
        with self.assertRaises(sanitizer.SanitizerProcessOutputLimitExceeded) as caught:
            run_script(source, max_output_bytes=128)
        self.assertEqual(str(caught.exception), sanitizer.OUTPUT_LIMIT_MESSAGE)

    def test_exact_output_boundary_is_allowed(self):
        source = "import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write(b'Q'*128)"
        result = run_script(source, max_output_bytes=128)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"Q" * 128)

    def test_nonzero_exit_is_returned_for_typed_failure_handling(self):
        result = run_script("import sys; sys.stdin.buffer.read(); sys.exit(7)")
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, b"")

    def test_macos_cleanup_recognizes_only_verified_zombie_groups(self):
        # Darwin returns EPERM when a group contains only unreaped zombies.
        # This must never permit a live descendant or an unverifiable group.
        leader_pid = 31337
        leader = unittest.mock.Mock(pid=leader_pid)
        cases = (
            (b"31337 31337 Z\n31338 31337 Z\n", True),
            (b"31337 31337 Z\n31338 31337 S\n", False),
            (b"31338 31337 Z\n", False),
            (b"invalid process table", False),
        )
        for stdout, allowed in cases:
            with (
                self.subTest(allowed=allowed, output=stdout),
                patch.object(sanitizer.sys, "platform", "darwin"),
                patch.object(
                    sanitizer.os, "killpg",
                    side_effect=PermissionError(errno.EPERM, "denied"),
                ),
                patch.object(
                    sanitizer, "_process_has_exited_without_reaping",
                    return_value=True,
                ),
                patch.object(
                    sanitizer.subprocess, "run",
                    return_value=subprocess.CompletedProcess([], 0, stdout, b""),
                ),
            ):
                if allowed:
                    sanitizer._stop_process_group(leader)
                    leader.kill.assert_not_called()
                else:
                    with self.assertRaises(sanitizer.SanitizerProcessExecutionError):
                        sanitizer._stop_process_group(leader)
                    leader.kill.assert_called()
                    leader.kill.reset_mock()

    def test_invalid_limits_fail_before_process_launch(self):
        command = (sys.executable, "-I", "-B", "-c", "pass")
        with patch.object(sanitizer.subprocess, "Popen") as launch:
            invalid = (
                ((), b"input", 1, 128, ENV.copy()),
                (command, b"", 1, 128, ENV.copy()),
                (command, b"input", True, 128, ENV.copy()),
                (command, b"input", 1, True, ENV.copy()),
                (command, b"input", 46, 128, ENV.copy()),
                (command, b"input", 1, 128, {"PATH": "\x00"}),
            )
            for cmd, contents, timeout, output, env in invalid:
                with self.subTest(timeout=timeout, output=output), self.assertRaises(
                    sanitizer.SanitizerProcessExecutionError
                ) as caught:
                    sanitizer.run_limited_converter(
                        cmd, contents, timeout_seconds=timeout,
                        max_output_bytes=output, environment=env,
                    )
                self.assertEqual(str(caught.exception), sanitizer.BLOCK_MESSAGE)
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
