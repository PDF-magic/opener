#!/usr/bin/env python3
"""opener-0309: enforce real worker memory ceilings without activating Maximum."""

from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import unittest
from unittest.mock import patch

import maximum_memory_limits as limits
from maximum_isolated_analysis import WORKER_MEMORY_MIB


ROOT = Path(__file__).resolve().parents[2]


class MaximumMemoryLimitsTests(unittest.TestCase):
    def test_memory_budget_matches_trusted_isolated_stage(self):
        self.assertEqual(limits.WORKER_MEMORY_BYTES, WORKER_MEMORY_MIB * limits.MiB)
        self.assertEqual(limits.WORKER_MEMORY_BYTES, 1024 * limits.MiB)

    def test_linux_configures_hard_address_space_ceiling(self):
        with patch.object(limits.sys, "platform", "linux"), patch.object(
            limits, "_tighten_limit"
        ) as tighten:
            limits.impose_maximum_worker_memory_limit()
        tighten.assert_called_once_with(resource.RLIMIT_AS, limits.WORKER_MEMORY_BYTES)

    def test_macos_mandates_periodic_resident_monitor(self):
        with patch.object(limits.sys, "platform", "darwin"), \
                patch.object(limits, "_tighten_limit") as tighten, \
                patch.object(limits, "_macos_resident_bytes", return_value=42), \
                patch.object(limits.signal, "signal") as register, \
                patch.object(limits.signal, "setitimer") as timer:
            limits.impose_maximum_worker_memory_limit()
        tighten.assert_not_called()
        register.assert_called_once_with(
            limits.signal.SIGALRM, limits._macos_memory_alarm)
        timer.assert_called_once_with(
            limits.signal.ITIMER_REAL,
            limits.MACOS_MONITOR_SECONDS, limits.MACOS_MONITOR_SECONDS)

    def test_guard_rejects_memory_over_target_without_printing_pdf_data(self):
        with patch.object(limits, "_macos_resident_bytes",
                          return_value=limits.WORKER_MEMORY_BYTES + 1):
            with self.assertRaises(limits.MaximumMemoryLimitError) as caught:
                limits._macos_memory_alarm(limits.signal.SIGALRM, None)
        self.assertNotIn("document", str(caught.exception))
        with patch.object(limits, "_macos_resident_bytes",
                          return_value=limits.WORKER_MEMORY_BYTES):
            limits._macos_memory_alarm(0, None)

    def test_unavailable_platform_never_continues_without_limit(self):
        with patch.object(limits.sys, "platform", "win32"), patch.object(
            limits, "_tighten_limit"
        ) as tighten:
            with self.assertRaises(limits.MaximumMemoryLimitError):
                limits.impose_maximum_worker_memory_limit()
        tighten.assert_not_called()

    def test_tightening_never_relaxes_existing_limit(self):
        hard = 512 * limits.MiB
        state = [(hard, hard)]
        def getlimit(_kind):
            return state[0]
        def setlimit(_kind, value):
            state[0] = value
        with patch.object(limits.resource, "getrlimit", side_effect=getlimit), \
                patch.object(limits.resource, "setrlimit", side_effect=setlimit):
            limits._tighten_limit(resource.RLIMIT_AS, limits.WORKER_MEMORY_BYTES)
        self.assertEqual(state[0], (hard, hard))

    def test_unavailable_or_invalid_limits_fail_closed(self):
        with patch.object(limits.sys, "platform", "linux"), \
                patch.object(limits.resource, "getrlimit", side_effect=OSError("sensitive")):
            with self.assertRaises(limits.MaximumMemoryLimitError):
                limits.impose_maximum_worker_memory_limit()
        for invalid in (0, -1, True, "1 GiB", None):
            with self.subTest(invalid=invalid), self.assertRaises(
                limits.MaximumMemoryLimitError
            ):
                limits._tighten_limit(resource.RLIMIT_AS, invalid)

    def test_worker_applies_guard_before_parser_import_and_never_changes_gate(self):
        worker = (ROOT / "maximum_isolated_worker.py").read_text()
        self.assertIn("impose_maximum_worker_memory_limit()", worker)
        self.assertLess(worker.index("impose_maximum_worker_memory_limit()"),
                        worker.index("from importlib import import_module"))
        self.assertIn("except BaseException:", worker)
        scanner = (ROOT / "scan-and-open.py").read_text()
        self.assertNotIn("maximum_memory_limits", scanner)
        self.assertNotIn("maximum_isolated_worker", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.MAXIMUM].selectable)

    @unittest.skipUnless(sys.platform == "linux", "Linux hard RLIMIT_AS validation")
    def test_real_os_rejects_allocation_beyond_worker_ceiling(self):
        script = """
import sys
sys.path.insert(0, sys.argv[1])
from maximum_memory_limits import impose_maximum_worker_memory_limit, WORKER_MEMORY_BYTES
impose_maximum_worker_memory_limit()
try:
    bytearray(WORKER_MEMORY_BYTES * 2)
except MemoryError:
    print('memory-ceiling-enforced')
    raise SystemExit(0)
raise SystemExit(3)
"""
        completed = subprocess.run(
            [sys.executable, "-I", "-B", "-c", script, str(ROOT)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15,
            close_fds=True, cwd="/",
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout.strip(), b"memory-ceiling-enforced")

    def test_real_worker_bootstraps_under_limits_without_pdf_input(self):
        # Only type names appear in diagnostics; never emit user paths/PDF bytes.
        script = """
import sys
sys.path.insert(0, sys.argv[1])
try:
    from maximum_isolated_worker import _apply_limits
    _apply_limits()
    print('memory-ready')
    import pypdf
    print('parser-ready')
except BaseException as error:
    print('bootstrap-failed:' + type(error).__name__ + ':' + str(error))
    raise SystemExit(2)
"""
        completed = subprocess.run(
            [sys.executable, "-I", "-B", "-c", script, str(ROOT)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15,
            close_fds=True, cwd="/",
        )
        self.assertEqual(completed.returncode, 0, completed.stdout.decode("ascii"))
        self.assertIn(b"parser-ready", completed.stdout)

    def test_real_worker_disarms_macos_watchdog_on_shutdown(self):
        # A successful worker disarms the real-time watchdog before teardown.
        worker = (ROOT / "maximum_isolated_worker.py").read_text()
        self.assertIn("signal.setitimer(signal.ITIMER_REAL, 0)", worker)
        self.assertLess(
            worker.index("code = main()"),
            worker.index("signal.setitimer(signal.ITIMER_REAL, 0)")
        )
        self.assertIn("except BaseException:", worker)

    def test_ci_runs_portable_child_checks_on_ubuntu(self):
        ci = (ROOT / ".github/workflows/consolidated-checks.yml").read_text()
        portable = ci.split("  macos-native-tests:", 1)[0]
        native = ci.split("  macos-native-tests:", 1)[1]
        self.assertIn("runs-on: ubuntu-latest", portable)
        self.assertIn("tests/maximum/memory-limits.py -v", portable)
        self.assertNotIn("tests/maximum/memory-limits.py -v", native)
        self.assertIn("tests/maximum/isolated-analysis.py -v", ci)
        self.assertIn("pypdf==5.9.0", ci)


if __name__ == "__main__":
    unittest.main()
