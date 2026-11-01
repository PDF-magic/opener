#!/usr/bin/env python3
"""Synthetic, non-destructive regression tests for explicit uninstall process stop."""

import importlib.util
from pathlib import Path
import os
import plistlib
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "stop_owned_background_processes", ROOT / "stop_owned_background_processes.py"
)
mod = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class StopOwnedBackgroundProcessesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="opener-0990-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.support = self.home / "Library/Application Support/Studio/allow-and-open"
        self.support.mkdir(parents=True)
        for name in ("scan-and-open.py", "allow-and-open.sh",
                     "update-malware-signatures.sh", "pdf-magic-native-host"):
            (self.support / name).write_text("test fixture")
        app = self.home / "Applications/PDF Magic Opener.app/Contents"
        (app / "MacOS").mkdir(parents=True)
        self.app_binary = app / "MacOS/PDFOpener"
        self.app_binary.write_text("test fixture")
        (app / "Info.plist").write_bytes(plistlib.dumps({
            "CFBundleIdentifier": "local.studio.brave-pdf-opener",
            "CFBundleExecutable": "PDFOpener",
        }))
        self.uid = os.getuid()
        self.platform = patch.object(mod.sys, "platform", "darwin")
        self.platform.start()
        self.addCleanup(self.platform.stop)
        self.no_root = patch.object(mod.os, "geteuid", return_value=501)
        self.no_root.start()
        self.addCleanup(self.no_root.stop)

    def record(self, pid, command):
        return mod.ProcessEntry(pid, self.uid, "Sat Oct 31 21:00:00 2026", command)

    def test_exact_owned_targets_and_shared_process_exclusions(self):
        owned = [
            (self.record(1001, "PDFOpener"), str(self.app_binary)),
            (self.record(1002, "pdf-magic-native-host"),
             str(self.support / "pdf-magic-native-host")),
            (self.record(1003, "/usr/bin/python3 " + str(self.support / "scan-and-open.py") +
                         " /tmp/a.pdf"), "/usr/bin/python3"),
            (self.record(1004, "/bin/bash " + str(self.support / "update-malware-signatures.sh")),
             "/bin/bash"),
            (self.record(1005, "/bin/bash " + str(self.support / "allow-and-open.sh") +
                         " /tmp/a.pdf"), "/bin/bash"),
        ]
        for entry, exe in owned:
            with self.subTest(pid=entry.pid):
                self.assertTrue(mod._managed(entry, self.home, exe))
        for entry, exe in [
            (self.record(1006, "/opt/homebrew/bin/clamscan /tmp/a.pdf"),
             "/opt/homebrew/bin/clamscan"),
            (self.record(1007, "/opt/homebrew/bin/freshclam"), "/opt/homebrew/bin/freshclam"),
            (self.record(1008, "/usr/bin/python3 /tmp/scan-and-open.py"),
             "/usr/bin/python3"),
            (self.record(1009, "/bin/bash " + str(self.support / "update-malware-signatures.sh")),
             "/bin/zsh"),
            (self.record(1010, "/usr/bin/python3 " + str(self.support / "scan-and-open.py") +
                         ".attacker"), "/usr/bin/python3"),
        ]:
            with self.subTest(pid=entry.pid):
                self.assertFalse(mod._managed(entry, self.home, exe))

    def test_inspection_is_read_only_and_stop_is_targeted(self):
        owned = self.record(1201, "/usr/bin/python3 " + str(self.support / "scan-and-open.py"))
        shared = self.record(1202, "/opt/homebrew/bin/clamscan")
        rows = [owned, shared]
        exe = {1201: "/usr/bin/python3", 1202: "/opt/homebrew/bin/clamscan"}
        signals = []
        def send(pid, sig):
            signals.append((pid, sig))
            rows.remove(owned)
        kwargs = dict(snapshot=lambda: list(rows), executable=exe.get, send=send,
                      sleep=lambda _: None, attempts=2)
        self.assertIn("no changes made", mod.stop_owned_processes(self.home, **kwargs))
        self.assertEqual(signals, [])
        self.assertIn("stopped", mod.stop_owned_processes(self.home, stop=True, **kwargs))
        self.assertEqual(signals, [(1201, signal.SIGTERM)])
        self.assertEqual(rows, [shared])
        self.assertIn("0 verified", mod.stop_owned_processes(self.home, **kwargs))

    def test_changed_pid_start_time_blocks_signal(self):
        row = self.record(1201, "/usr/bin/python3 " + str(self.support / "scan-and-open.py"))
        swapped = mod.ProcessEntry(row.pid, row.uid, "Sat Oct 31 21:01:00 2026", row.command)
        calls = 0
        def snapshot():
            nonlocal calls
            calls += 1
            return [row] if calls == 1 else [swapped]
        signals = []
        with self.assertRaises(mod.ProcessStopRefused):
            mod.stop_owned_processes(self.home, stop=True, snapshot=snapshot,
                                     executable=lambda _: "/usr/bin/python3",
                                     send=lambda pid, sig: signals.append((pid, sig)))
        self.assertEqual(signals, [])

    def test_unknown_executable_symlink_and_foreign_owner_refused(self):
        row = self.record(1201, "/usr/bin/python3 " + str(self.support / "scan-and-open.py"))
        with self.assertRaises(mod.ProcessStopRefused):
            mod._managed(row, self.home, "/bin/bash")
        script = self.support / "scan-and-open.py"
        script.unlink()
        script.symlink_to(self.support / "allow-and-open.sh")
        with self.assertRaises(mod.ProcessStopRefused):
            mod._managed(row, self.home, "/usr/bin/python3")
        script.unlink()
        script.write_text("test fixture")
        with patch.object(mod.os, "getuid", return_value=self.uid + 5):
            self.assertFalse(mod._managed(row, self.home, "/usr/bin/python3"))

    def test_unresponsive_process_is_not_killed_or_claimed_stopped(self):
        row = self.record(1201, "/usr/bin/python3 " + str(self.support / "scan-and-open.py"))
        sent = []
        with self.assertRaisesRegex(mod.ProcessStopRefused, "still active"):
            mod.stop_owned_processes(
                self.home, stop=True, snapshot=lambda: [row],
                executable=lambda _: "/usr/bin/python3",
                send=lambda pid, sig: sent.append((pid, sig)), sleep=lambda _: None, attempts=2
            )
        self.assertEqual(sent, [(1201, signal.SIGTERM)])

    def test_safe_failures_and_cli_confirmation(self):
        with patch.object(mod.os, "geteuid", return_value=0):
            with self.assertRaises(mod.ProcessStopRefused):
                mod.stop_owned_processes(self.home, snapshot=lambda: [])
        with patch.object(mod.sys, "platform", "linux"):
            with self.assertRaises(mod.ProcessStopRefused):
                mod.stop_owned_processes(self.home, snapshot=lambda: [])
        with patch("builtins.input", return_value="NO"):
            self.assertEqual(mod.main(["--stop"]), 1)
        source = (ROOT / "stop_owned_background_processes.py").read_text()
        self.assertNotIn("shell=True", source)
        self.assertNotIn("SIGKILL", source.replace("escalate to SIGKILL", ""))
        self.assertNotIn("pkill", source)
        self.assertNotIn("killall", source)

    def test_ps_parser_and_ci_docs_wiring(self):
        response = subprocess.CompletedProcess(
            [], 0, " 1201 501 Sat Oct 31 21:00:00 2026 /usr/bin/python3 /a b/scan-and-open.py\n", ""
        )
        with patch.object(mod.subprocess, "run", return_value=response) as run:
            rows = mod.list_processes()
        self.assertEqual(rows[0].pid, 1201)
        self.assertEqual(rows[0].command, "/usr/bin/python3 /a b/scan-and-open.py")
        self.assertIn("-ww", run.call_args.args[0])
        guide = (ROOT / "docs/uninstall-procedure.md").read_text()
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("python3 stop_owned_background_processes.py --stop", guide)
        self.assertIn("PYTHONPATH=. python3 tests/general/stop-owned-processes.py -v", ci)


if __name__ == "__main__":
    unittest.main()
