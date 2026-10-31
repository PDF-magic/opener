#!/usr/bin/env python3
"""opener-0834: keep final file validation adjacent to native handoff."""

from contextlib import ExitStack
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("final_handoff_gate", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class FinalHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="final-handoff-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.file = self.root / "report.pdf"
        self.contents = b"%PDF-1.4\noriginal safe bytes\n%%EOF\n"
        self.file.write_bytes(self.contents)

    def fixtures(self, stack, *, fallback=None, availability=None, record=None, launch=None):
        stack.enter_context(patch.object(gate, "CACHE_DB", self.root / "clean.sqlite3"))
        stack.enter_context(patch.object(gate, "SCAN_REQUEST_DB", self.root / "requests.sqlite3"))
        stack.enter_context(patch.object(gate, "intended_destination", return_value="com.brave.Browser"))
        stack.enter_context(patch.object(gate, "pdf_fallback_application", return_value=fallback))
        stack.enter_context(patch.object(gate, "verify_launch_target"))
        stack.enter_context(patch.object(gate, "verify_local_file_available",
                                        side_effect=availability))
        stack.enter_context(patch.object(gate, "record_scan_destination",
                                        side_effect=record))
        stack.enter_context(patch.object(gate, "remove_quarantine"))
        stack.enter_context(patch.object(gate, "scan_engine_version", return_value=None))
        stack.enter_context(patch.object(gate, "read_signature_database_version",
                                        return_value=None))
        stack.enter_context(patch.object(gate, "run_scan_command", return_value=
            subprocess.CompletedProcess([], 0, "report.pdf: OK", "")))
        return stack.enter_context(patch.object(gate, "launch_clean_file",
                                                side_effect=launch))

    def test_final_validation_follows_slow_pdf_availability_probe(self):
        events = []
        original_verify = gate.verify_file_integrity

        def available(path):
            events.append("availability")

        def verify(*args, **kwargs):
            events.append("integrity")
            return original_verify(*args, **kwargs)

        def launch(*args, **kwargs):
            events.append("launch")

        with ExitStack() as stack:
            self.fixtures(stack, availability=available, launch=launch)
            stack.enter_context(patch.object(gate, "verify_file_integrity",
                                             side_effect=verify))
            result = gate.scan_and_open(str(self.file), "/scanner")
        self.assertEqual(result.status, "clean")
        self.assertEqual(events[-2:], ["integrity", "launch"])
        self.assertLess(events.index("availability"), len(events) - 2)

    def test_byte_identical_replacement_during_last_availability_check_blocks(self):
        probes = []
        launches = []
        original = self.contents

        def available(path):
            probes.append(path)
            if len(probes) == 3:
                displaced = self.root / "previous.pdf"
                self.file.rename(displaced)
                self.file.write_bytes(original)

        with ExitStack() as stack:
            launch = self.fixtures(stack, availability=available,
                                   launch=lambda *args, **kwargs: launches.append(args))
            with self.assertRaisesRegex(RuntimeError, "changed"):
                gate.scan_and_open(str(self.file), "/scanner")
        self.assertEqual(len(probes), 3)
        launch.assert_not_called()
        self.assertEqual(launches, [])
        self.assertEqual(self.file.read_bytes(), original)

    def test_fallback_audit_replacement_is_revalidated_before_second_launch(self):
        destinations = []
        launches = []

        def record(destination):
            destinations.append(destination)
            if destination == "com.apple.Preview":
                displaced = self.root / "previous.pdf"
                self.file.rename(displaced)
                self.file.write_bytes(self.contents)

        def launch(path, *, target_app=None):
            launches.append(target_app)
            if target_app == "com.brave.Browser":
                raise OSError("primary browser unavailable")

        with ExitStack() as stack:
            native = self.fixtures(stack, fallback="com.apple.Preview",
                                   record=record, launch=launch)
            with self.assertRaisesRegex(RuntimeError, "changed"):
                gate.scan_and_open(str(self.file), "/scanner")
        self.assertEqual(destinations,
                         ["com.brave.Browser", "com.apple.Preview"])
        self.assertEqual(launches, ["com.brave.Browser"])
        self.assertEqual(native.call_count, 1)
        self.assertEqual(self.file.read_bytes(), self.contents)


if __name__ == "__main__":
    unittest.main()
