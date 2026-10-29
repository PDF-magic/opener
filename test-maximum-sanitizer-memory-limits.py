#!/usr/bin/env python3
"""opener-0491: bound memory use in the optional Maximum sanitizer process."""
import os
import resource
import signal
import sys
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

    def test_ci_runs_memory_checks_on_linux_and_macos(self):
        from pathlib import Path
        workflow = (Path(__file__).parent / ".github/workflows/maximum-sanitized-copy.yml").read_text()
        self.assertIn("ubuntu-latest", workflow)
        self.assertIn("macos-latest", workflow)
        self.assertGreaterEqual(workflow.count("test-maximum-sanitizer-memory-limits.py -v"), 2)


if __name__ == "__main__":
    unittest.main()
