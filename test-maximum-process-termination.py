#!/usr/bin/env python3
"""opener-0312: actually kill runaway Maximum worker process groups."""
import errno
import os
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import maximum_process_termination as guard


ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/nonexistent",
    "LANG": "C",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONNOUSERSITE": "1",
}


def run_script(source, *, timeout=2, contents=b"safe"):
    return guard.run_limited_worker(
        (sys.executable, "-I", "-B", "-c", source), contents,
        timeout_seconds=timeout, environment=ENV.copy())


class MaximumProcessTerminationTests(unittest.TestCase):
    def test_success_uses_separate_process_and_only_returns_bounded_output(self):
        result = run_script(
            "import os,sys; sys.stdin.buffer.read(); "
            "sys.stdout.write(str(os.getpid()))")
        self.assertTrue(result.isdigit())
        self.assertNotEqual(int(result), os.getpid())
        self.assertLessEqual(len(result), guard.MAX_OUTPUT_BYTES)

    def test_deadline_terminates_silent_hung_child_and_reaps_it(self):
        killed = []
        real_kill = os.killpg
        def kill(pgid, sig):
            killed.append((pgid, sig))
            return real_kill(pgid, sig)
        start = time.monotonic()
        with patch.object(guard.os, "killpg", side_effect=kill):
            with self.assertRaises(guard.MaximumProcessTerminationError):
                run_script("import time; time.sleep(20)", timeout=1)
        self.assertLess(time.monotonic() - start, 5)
        self.assertTrue(killed)
        self.assertEqual(killed[0][1], signal.SIGKILL)
        self.assertNotEqual(killed[0][0], os.getpgrp())

    def test_child_that_spawns_grandchild_cannot_escape_timeout(self):
        killed = []
        real_kill = os.killpg
        def kill(pgid, sig):
            killed.append(pgid)
            return real_kill(pgid, sig)
        script = (
            "import subprocess,sys,time; "
            "subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)']); "
            "sys.stdout.write('spawned'); sys.stdout.flush(); time.sleep(20)"
        )
        with patch.object(guard.os, "killpg", side_effect=kill):
            with self.assertRaises(guard.MaximumProcessTerminationError):
                run_script(script, timeout=1)
        self.assertTrue(killed)
        self.assertNotIn(os.getpgrp(), killed)
        # Descendant processes may be briefly zombies in CI; demonstrate the
        # group was explicitly targeted, not infer cleanup solely from a PID.
        self.assertEqual(killed[0], killed[-1])

    def test_success_also_cleans_leftover_worker_descendants(self):
        groups = []
        real_kill = os.killpg
        def kill(pgid, sig):
            groups.append(pgid)
            return real_kill(pgid, sig)
        script = (
            "import subprocess,sys; "
            "subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)'], "
            "stdout=subprocess.DEVNULL); "
            "sys.stdin.buffer.read(); sys.stdout.write('ok')"
        )
        with patch.object(guard.os, "killpg", side_effect=kill):
            self.assertEqual(run_script(script), b"ok")
        self.assertEqual(len(groups), 1)
        self.assertNotEqual(groups[0], os.getpgrp())

    def test_stdout_overflow_is_killed_while_reading_not_after_exit(self):
        killed = []
        real_kill = os.killpg
        with patch.object(guard.os, "killpg", side_effect=lambda pid, sig: (
                killed.append(pid), real_kill(pid, sig))[-1]):
            with self.assertRaises(guard.MaximumProcessTerminationError):
                run_script(
                    "import sys,time; sys.stdout.write('X'*1000000); "
                    "sys.stdout.flush(); time.sleep(20)")
        self.assertTrue(killed)

    def test_exact_cumulative_output_limit_and_first_excess_byte(self):
        # A fully complete boundary-size response is allowed; no temporary
        # parent read may exceed the remaining budget plus one byte.
        payload = run_script(
            "import sys;sys.stdin.buffer.read();sys.stdout.write('Q'*4096)"
        )
        self.assertEqual(payload, b"Q" * guard.MAX_OUTPUT_BYTES)
        with self.assertRaises(guard.MaximumProcessTerminationError) as error:
            run_script(
                "import sys;sys.stdin.buffer.read();sys.stdout.write('Q'*4097)"
            )
        self.assertEqual(str(error.exception), guard.BLOCK_MESSAGE)

    def test_output_limit_is_cumulative_across_separate_writes(self):
        accepted = run_script(
            "import os,time;os.read(0,4);os.write(1,b'A'*3072);"
            "time.sleep(0.02);os.write(1,b'B'*1024)"
        )
        self.assertEqual(accepted, b"A"*3072 + b"B"*1024)
        with self.assertRaises(guard.MaximumProcessTerminationError):
            run_script(
                "import os,time;os.read(0,4);os.write(1,b'A'*3072);"
                "time.sleep(0.02);os.write(1,b'B'*1025)"
            )

    def test_abnormal_exit_is_blocked_and_worker_group_cleaned(self):
        with self.assertRaises(guard.MaximumProcessTerminationError):
            run_script("import sys; sys.exit(7)")
        with self.assertRaises(guard.MaximumProcessTerminationError):
            run_script("import os,signal; os.kill(os.getpid(),signal.SIGKILL)")

    def test_stdin_pipe_cannot_hang_if_worker_does_not_read(self):
        start = time.monotonic()
        with self.assertRaises(guard.MaximumProcessTerminationError):
            run_script("import time; time.sleep(20)", timeout=1,
                       contents=b"p" * (1024 * 1024))
        self.assertLess(time.monotonic() - start, 5)

    def test_fail_closed_on_bad_inputs_before_any_process_launch(self):
        cases = (
            (("python",), b"x", 1, ENV),
            ((sys.executable, "-c", "pass"), b"", 1, ENV),
            ((sys.executable, "-c", "pass"), "bad", 1, ENV),
            ((sys.executable, "-c", "pass"), b"x", 0, ENV),
            ((sys.executable, "-c", "pass"), b"x", 31, ENV),
            ((sys.executable, "-c", "pass"), b"x", True, ENV),
            ((sys.executable, "-c", "pass"), b"x", 1, {"BAD": 2}),
        )
        with patch.object(guard.subprocess, "Popen") as spawn:
            for command, contents, timeout, env in cases:
                with self.subTest(timeout=timeout, env=env), self.assertRaises(
                    guard.MaximumProcessTerminationError
                ):
                    guard.run_limited_worker(
                        command, contents, timeout_seconds=timeout, environment=env)
            spawn.assert_not_called()

    def test_cleanup_failure_is_never_reported_success(self):
        with patch.object(guard.os, "killpg", side_effect=PermissionError("private")):
            with self.assertRaises(guard.MaximumProcessTerminationError):
                run_script("import sys; sys.stdin.buffer.read(); print('ok')")

    def test_test_diagnostics_have_only_fixed_non_payload_categories(self):
        from maximum_process_termination import MaximumProcessTerminationError
        secret = "Private PDF text and local /Users/name"
        opaque = MaximumProcessTerminationError(secret, category=secret)
        self.assertEqual(str(opaque), guard.BLOCK_MESSAGE)
        self.assertEqual(opaque.category, "unknown")
        with self.assertRaises(MaximumProcessTerminationError) as result:
            run_script("import sys; sys.exit(7)")
        self.assertEqual(result.exception.category, "worker-exit")
        self.assertNotIn("Users", str(result.exception))

    def test_macos_eperm_requires_verified_zombie_leader(self):
        process = type("FakeWorker", (), {
            "pid": 101, "returncode": None, "kill": lambda self: None,
        })()
        verified = subprocess.CompletedProcess(
            ("ps",), 0, b"101 101 Z+\n102 101 Z\n202 202 S+\n"
        )
        invalid = (
            b"",
            b"202 202 Z\n",
            b"102 101 Z\n",
            b"101 202 Z\n102 101 Z\n",
            b"101 101 S\n",
            b"101 101 Z\n102 101 S\n",
            b"not-a-process-record\n",
        )
        with patch.object(guard.sys, "platform", "darwin"), \
                patch.object(guard.os, "killpg",
                             side_effect=PermissionError(errno.EPERM, "private")):
            with patch.object(guard.subprocess, "run", return_value=verified) as probe:
                guard._stop_group(process)
                self.assertEqual(
                    probe.call_args.args[0],
                    ("/bin/ps", "-A", "-o", "pid=,pgid=,stat="),
                )
            for table in invalid:
                with self.subTest(table=table), \
                        patch.object(guard.subprocess, "run", return_value=(
                            subprocess.CompletedProcess(("ps",), 0, table)
                        )):
                    with self.assertRaises(guard.MaximumProcessTerminationError):
                        guard._stop_group(process)

    def test_only_opt_in_maximum_uses_new_supervisor(self):
        from pathlib import Path
        source = (Path(__file__).parent / "scan-and-open.py").read_text()
        self.assertNotIn("maximum_process_termination", source)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.MAXIMUM].selectable)


if __name__ == "__main__":
    unittest.main()
