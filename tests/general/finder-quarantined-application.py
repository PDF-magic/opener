#!/usr/bin/env python3
"""opener-0824: Finder Quick Action handoff for quarantined .app bundles.

Exercise the real Python scan gate against disposable application bundles.
ClamAV and Launch Services are replaced only at their external process
boundaries; on macOS the test uses real com.apple.quarantine xattrs.
No application is executed, no Finder preferences are modified, and no
installed scanner, user documents, or default handlers are accessed.
"""

from contextlib import ExitStack, nullcontext
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("finder_app_scan_gate",
                                               ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

ATTRIBUTE = "com.apple.quarantine"
MARKER = b"0081;00000000;PDFMagicOpener;00000000-0000-0000-0000-000000000000"
MACOS = sys.platform == "darwin"


def quarantine_bytes(path):
    result = subprocess.run(
        ["/usr/bin/xattr", "-px", ATTRIBUTE, str(path)],
        capture_output=True, check=True, timeout=10
    )
    return bytes.fromhex(result.stdout.decode("ascii"))


def apply_quarantine(path):
    subprocess.run(
        ["/usr/bin/xattr", "-wx", ATTRIBUTE, MARKER.hex(), str(path)],
        capture_output=True, check=True, timeout=10
    )


class FinderQuarantinedApplicationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="opener-finder-app-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.app = self.root / "Harmless Finder Test \u2013 Sample.app"
        executable_dir = self.app / "Contents" / "MacOS"
        executable_dir.mkdir(parents=True)
        self.executable = executable_dir / "Sample"
        self.executable.write_bytes(b"#!/bin/sh\nexit 0\n")
        self.executable.chmod(0o755)
        with (self.app / "Contents" / "Info.plist").open("wb") as stream:
            plistlib.dump({
                "CFBundleIdentifier": "org.pdfmagic.safe-finder-test",
                "CFBundleExecutable": "Sample",
                "CFBundlePackageType": "APPL",
            }, stream)
        self.original = self.executable.read_bytes()
        self.quarantined = False

    def tag_bundle(self):
        if MACOS:
            apply_quarantine(self.app)
            apply_quarantine(self.executable)
            self.quarantined = True
            self.assert_quarantine_intact()

    def assert_quarantine_intact(self):
        if self.quarantined:
            self.assertEqual(quarantine_bytes(self.app), MARKER)
            self.assertEqual(quarantine_bytes(self.executable), MARKER)

    def exercise_gate(self, *, verdict="clean", cached=False, mutate=False,
                      launch_failure=False):
        events = []
        with ExitStack() as stack:
            stack.enter_context(patch.object(gate, "CACHE_DB",
                                             self.root / "cache.sqlite3"))
            stack.enter_context(patch.object(gate, "SCAN_REQUEST_DB",
                                             self.root / "requests.sqlite3"))
            stack.enter_context(patch.object(gate, "scan_slot",
                                             side_effect=lambda: nullcontext()))
            stack.enter_context(patch.object(gate, "active_scan_lock",
                                             side_effect=lambda unused: nullcontext()))
            stack.enter_context(patch.object(gate, "scan_engine_version",
                                             return_value=None))
            stack.enter_context(patch.object(gate, "read_signature_database_version",
                                             return_value=None))
            stack.enter_context(patch.object(
                gate, "record_scan_destination",
                side_effect=lambda destination: events.append(("destination", destination))
            ))
            stack.enter_context(patch.object(
                gate, "record_opened_document_origin",
                side_effect=lambda origin: events.append(("opened", origin))
            ))
            stack.enter_context(patch.object(
                gate, "pdf_fallback_application",
                side_effect=AssertionError("App bundles cannot use the PDF fallback")
            ))
            stack.enter_context(patch.object(
                gate, "verify_local_file_available",
                side_effect=AssertionError("App bundles cannot use the PDF cloud gate")
            ))
            original_verify = gate.verify_launch_target

            def verify(path, target_app=None):
                self.assertEqual(path, self.app)
                self.assertIsNone(target_app)
                self.assert_quarantine_intact()
                events.append(("verified", str(path)))
                return original_verify(path, target_app=target_app)

            stack.enter_context(patch.object(gate, "verify_launch_target",
                                             side_effect=verify))
            original_retention_hook = gate.remove_quarantine
            retention_hook = stack.enter_context(
                patch.object(gate, "remove_quarantine",
                             wraps=original_retention_hook)
            )

            def scan(command, **kwargs):
                self.assertEqual(command[0], "/synthetic-clamscan")
                self.assertEqual(command[-2:], ["--", str(self.app)])
                self.assertIn("--recursive", command)
                self.assertIn("--follow-dir-symlinks=2", command)
                self.assertIn("--follow-file-symlinks=2", command)
                self.assertEqual(kwargs["timeout"], gate.ACTIVE_SCAN_POLICY.snapshot().other_timeout_seconds)
                self.assert_quarantine_intact()
                events.append(("scanned", str(self.app)))
                if mutate:
                    self.executable.write_bytes(self.original + b"# changed")
                if verdict == "timeout":
                    raise subprocess.TimeoutExpired(command, 1)
                if verdict == "malware":
                    return subprocess.CompletedProcess(
                        command, 1, "Sample: Eicar-Test-Signature FOUND", ""
                    )
                if verdict == "unscannable":
                    return subprocess.CompletedProcess(command, 2, "ERROR", "")
                return subprocess.CompletedProcess(command, 0, "Sample: OK", "")

            scan_mock = stack.enter_context(
                patch.object(gate, "run_scan_command", side_effect=scan)
            )

            def launch(path, target_app=None):
                self.assertEqual(path, self.app)
                self.assertIsNone(target_app)
                self.assert_quarantine_intact()
                events.append(("launch", str(path)))
                if launch_failure:
                    raise OSError("Synthetic Launch Services failure")

            launch_mock = stack.enter_context(
                patch.object(gate, "launch_clean_file", side_effect=launch)
            )

            def invoke():
                return gate.scan_and_open(str(self.app), "/synthetic-clamscan")

            if verdict == "clean" and not mutate and not launch_failure:
                self.assertFalse(invoke().from_cache)
                if cached:
                    self.assertTrue(invoke().from_cache)
            else:
                message = ("timed out" if verdict == "timeout" else
                           "Malware" if verdict == "malware" else
                           "could not finish" if verdict == "unscannable" else
                           "changed" if mutate else "could not open")
                with self.assertRaisesRegex(RuntimeError, message):
                    invoke()
            self.assertEqual(scan_mock.call_count, 1)
            self.assertEqual(launch_mock.call_count,
                             2 if cached else
                             1 if verdict == "clean" and not mutate else 0)
            self.assertEqual(retention_hook.call_count,
                             2 if cached else
                             1 if verdict == "clean" and not mutate else 0)
        self.assert_quarantine_intact()
        return events

    def test_quick_action_shell_forwards_bundle_and_finder_origin(self):
        # Only a disposable copy of the real Finder shell entry point runs.
        # These two harmless stubs cannot scan or launch an application.
        with tempfile.TemporaryDirectory(prefix="finder-wrapper-") as directory:
            folder = Path(directory)
            wrapper = folder / "allow-and-open.sh"
            shutil.copyfile(ROOT / "allow-and-open.sh", wrapper)
            (folder / "record-scan-origin.py").write_text(
                "import os\nfrom pathlib import Path\n"
                "Path(os.environ['ORIGIN_RECEIPT']).write_text("
                "os.environ.get('PDF_MAGIC_REQUEST_ORIGIN', ''))\n",
                encoding="utf-8"
            )
            (folder / "scan-and-open.py").write_text(
                "import json, os, sys\nfrom pathlib import Path\n"
                "Path(os.environ['PATH_RECEIPT']).write_text("
                "json.dumps(sys.argv[1:]))\n",
                encoding="utf-8"
            )
            path_receipt = folder / "path.json"
            origin_receipt = folder / "origin.txt"
            env = dict(os.environ, PDF_MAGIC_REQUEST_ORIGIN="finder",
                       PATH_RECEIPT=str(path_receipt),
                       ORIGIN_RECEIPT=str(origin_receipt))
            self.tag_bundle()
            subprocess.run(
                ["/bin/bash", str(wrapper), str(self.app)],
                check=True, capture_output=True, timeout=20, env=env
            )
            self.assertEqual(json.loads(path_receipt.read_text(encoding="utf-8")),
                             [str(self.app)])
            self.assertEqual(origin_receipt.read_text(encoding="utf-8"),
                             "finder")
            self.assert_quarantine_intact()

    def test_installer_keeps_finder_quick_action_connected_to_shared_scan_gate(self):
        script = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
        self.assertIn("PDF_MAGIC_REQUEST_ORIGIN=finder", script)
        self.assertIn("'com.apple.RunShellScript'", script)
        self.assertIn("parameters['inputMethod'] = 1", script)
        self.assertIn('"$@"', script)
        self.assertIn('"$script_dir/allow-and-open.sh"', script)
        wrapper = (ROOT / "allow-and-open.sh").read_text(encoding="utf-8")
        self.assertIn('record-scan-origin.py" "$@"', wrapper)
        self.assertIn('scan-and-open.py" "$@"', wrapper)

    def test_clean_quarantined_app_is_handed_off_after_recursive_scan_and_cached(self):
        self.tag_bundle()
        events = self.exercise_gate(cached=True)
        self.assertEqual(events.count(("scanned", str(self.app))), 1)
        self.assertEqual(events.count(("launch", str(self.app))), 2)
        self.assertEqual(events.count(("destination", self.app.name)), 2)
        self.assertEqual(events.count(("opened", "original")), 2)
        self.assertLess(events.index(("scanned", str(self.app))),
                        events.index(("verified", str(self.app))))
        self.assertLess(events.index(("verified", str(self.app))),
                        events.index(("launch", str(self.app))))
        self.assertEqual(self.executable.read_bytes(), self.original)

    def test_malware_timeout_and_unscannable_bundle_never_launch(self):
        self.tag_bundle()
        for verdict in ("malware", "timeout", "unscannable"):
            with self.subTest(verdict=verdict):
                events = self.exercise_gate(verdict=verdict)
                self.assertNotIn(("launch", str(self.app)), events)
                self.assertFalse(any(event[0] == "opened" for event in events))

    def test_changed_bundle_member_blocks_open_without_clearing_quarantine(self):
        self.tag_bundle()
        events = self.exercise_gate(mutate=True)
        self.assertNotIn(("launch", str(self.app)), events)
        self.assert_quarantine_intact()

    def test_failed_native_handoff_keeps_quarantine_and_no_open_audit(self):
        self.tag_bundle()
        events = self.exercise_gate(launch_failure=True)
        self.assertIn(("launch", str(self.app)), events)
        self.assertFalse(any(event[0] == "opened" for event in events))

    def test_unscannable_bundle_entries_fail_before_scan_or_launch(self):
        self.tag_bundle()
        resources = self.app / "Contents" / "Resources"
        resources.mkdir()
        empty = resources / "empty.dat"
        outside = self.root / "outside.dat"
        outside.write_bytes(b"unrelated synthetic file")
        for kind in ("empty", "outside-symlink"):
            with self.subTest(kind=kind):
                if kind == "empty":
                    empty.write_bytes(b"")
                else:
                    empty.unlink()
                    (resources / "outside").symlink_to(outside)
                with patch.object(gate, "scan_slot",
                                  side_effect=lambda: nullcontext()), \
                     patch.object(gate, "record_scan_destination"), \
                     patch.object(gate, "run_scan_command") as scanner, \
                     patch.object(gate, "launch_clean_file") as launcher, \
                     patch.object(gate, "remember_clean") as cache:
                    with self.assertRaisesRegex(
                        RuntimeError, "zero-length|link outside the bundle"
                    ):
                        gate.scan_and_open(str(self.app), "/synthetic-clamscan")
                scanner.assert_not_called()
                launcher.assert_not_called()
                cache.assert_not_called()
                self.assert_quarantine_intact()

    def test_native_bundle_launch_does_not_invoke_pdf_browser_preferences(self):
        import file_launcher
        with patch.object(file_launcher, "pdf_target_application",
                          side_effect=AssertionError("PDF preferences were read")), \
             patch.object(file_launcher, "require_executable_path") as executable, \
             patch.object(file_launcher.subprocess, "run") as run:
            file_launcher.launch_clean_file(self.app)
        executable.assert_called_once_with(file_launcher.NATIVE_LAUNCHER)
        run.assert_called_once_with(
            [str(file_launcher.NATIVE_LAUNCHER), str(self.app)],
            check=True, timeout=30
        )


if __name__ == "__main__":
    unittest.main()
