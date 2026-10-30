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
