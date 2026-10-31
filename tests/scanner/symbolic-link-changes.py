#!/usr/bin/env python3
"""opener-0829: selected symlink changes invalidate otherwise clean scans."""

from contextlib import contextmanager, ExitStack
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("scan_gate_selected_links", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class SelectedSymlinkChangesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="opener-selected-links-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        contents = b"%PDF-1.4\n1 0 obj <</Type /Catalog>> endobj\n%%EOF\n"
        self.first = self.root / "first.pdf"
        self.second = self.root / "second.pdf"
        self.first.write_bytes(contents)
        self.second.write_bytes(contents)
        self.alias = self.root / "selected.pdf"
        self.alias.symlink_to(self.first)
        self.launched = []

    def replace_link(self, link, target):
        replacement = self.root / "replacement-link"
        replacement.symlink_to(target)
        replacement.replace(link)

    def fixture(self, stack, scan_callback=None):
        stack.enter_context(patch.object(gate, "CACHE_DB", self.root / "cache.sqlite"))
        stack.enter_context(patch.object(gate, "SCAN_REQUEST_DB", self.root / "audit.sqlite"))
        stack.enter_context(patch.object(gate, "intended_destination", return_value="com.brave.Browser"))
        stack.enter_context(patch.object(gate, "pdf_fallback_application", return_value=None))
        stack.enter_context(patch.object(gate, "record_scan_destination"))
        stack.enter_context(patch.object(gate, "verify_launch_target"))
        stack.enter_context(patch.object(gate, "verify_local_file_available"))
        stack.enter_context(patch.object(gate, "scan_engine_version", return_value=None))
        stack.enter_context(patch.object(gate, "read_signature_database_version", return_value=None))
        stack.enter_context(patch.object(gate, "launch_clean_file",
                                         side_effect=lambda *a, **kw: self.launched.append(a)))
        def run(command, **kwargs):
            if scan_callback:
                scan_callback()
            return subprocess.CompletedProcess(command, 0, "selected.pdf: OK", "")
        stack.enter_context(patch.object(gate.subprocess, "run", side_effect=run))

    def test_normal_symlink_and_regular_path_still_work(self):
        original = gate.symbolic_link_identity(self.alias)
        # macOS aliases /var to /private/var; compare canonical identities
        # rather than assuming the temporary root has no ancestor symlinks.
        self.assertEqual(original[0], self.first.resolve(strict=True))
        self.assertEqual(original, gate.symbolic_link_identity(self.alias))
        self.assertEqual(gate.symbolic_link_identity(self.first)[0],
                         self.first.resolve(strict=True))
        with ExitStack() as stack:
            self.fixture(stack)
            self.assertFalse(gate.scan_and_open(self.alias, "/scanner").from_cache)
            self.assertTrue(gate.scan_and_open(self.alias, "/scanner").from_cache)
        self.assertEqual(len(self.launched), 2)

    def test_retarget_with_identical_bytes_changes_identity(self):
        before = gate.symbolic_link_identity(self.alias)
        self.replace_link(self.alias, self.second)
        self.assertNotEqual(before, gate.symbolic_link_identity(self.alias))

    def test_intermediate_symlink_retarget_is_detected(self):
        middle = self.root / "middle"
        middle.symlink_to(self.first)
        self.alias.unlink()
        self.alias.symlink_to(middle)
        before = gate.symbolic_link_identity(self.alias)
        # Include the selected alias and intermediate alias; macOS may also
        # contribute OS-managed links in ancestor directories.
        self.assertGreaterEqual(len(before[1]), 2)
        self.replace_link(middle, self.second)
        self.assertNotEqual(before, gate.symbolic_link_identity(self.alias))

    def test_scanner_time_retarget_blocks_cache_and_open(self):
        with ExitStack() as stack:
            self.fixture(stack, lambda: self.replace_link(self.alias, self.second))
            saved = stack.enter_context(patch.object(gate, "remember_clean"))
            with self.assertRaisesRegex(RuntimeError, "file changed while checking"):
                gate.scan_and_open(self.alias, "/scanner")
        saved.assert_not_called()
        self.assertEqual(self.launched, [])

    def test_cache_hit_retarget_blocks_open(self):
        with ExitStack() as stack:
            self.fixture(stack)
            def swap_on_lookup(_digest):
                self.replace_link(self.alias, self.second)
                return True
            stack.enter_context(patch.object(gate, "cached_clean", side_effect=swap_on_lookup))
            stack.enter_context(patch.object(gate, "cached_scan", return_value=gate.CleanScanResult(
                status="clean", from_cache=True)))
            scanned = stack.enter_context(patch.object(gate, "run_scan_command"))
            with self.assertRaisesRegex(RuntimeError, "file changed while checking"):
                gate.scan_and_open(self.alias, "/scanner")
        scanned.assert_not_called()
        self.assertEqual(self.launched, [])

    def test_queue_time_retarget_blocks_before_scanner(self):
        @contextmanager
        def swapped_queue():
            self.replace_link(self.alias, self.second)
            yield
        with ExitStack() as stack:
            stack.enter_context(patch.object(gate, "scan_slot", side_effect=swapped_queue))
            scanner = stack.enter_context(patch.object(gate, "run_scan_command"))
            launched = stack.enter_context(patch.object(gate, "launch_clean_file"))
            with self.assertRaisesRegex(RuntimeError, "file changed while checking"):
                gate.scan_and_open(self.alias, "/scanner")
        scanner.assert_not_called()
        launched.assert_not_called()

    def test_dangling_and_cyclic_links_are_path_free_errors(self):
        self.alias.unlink()
        self.alias.symlink_to(self.root / "missing.pdf")
        with self.assertRaisesRegex(RuntimeError, "file changed while checking") as raised:
            gate.symbolic_link_identity(self.alias)
        self.assertNotIn(str(self.root), str(raised.exception))
        self.alias.unlink()
        self.alias.symlink_to(self.alias)
        with self.assertRaisesRegex(RuntimeError, "file changed while checking"):
            gate.symbolic_link_identity(self.alias)


if __name__ == "__main__":
    unittest.main()
