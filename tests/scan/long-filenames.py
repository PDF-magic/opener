#!/usr/bin/env python3
"""opener-0846: real filesystem filename-byte limits at scan admission and handoff."""

from contextlib import ExitStack, redirect_stderr
import errno
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("long_filename_scan_gate", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class ExtremelyLongFilenamesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="opener-0846-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        try:
            self.max_bytes = os.pathconf(str(self.root), "PC_NAME_MAX")
        except (OSError, ValueError):
            self.skipTest("The filesystem does not report a filename byte limit")
        if self.max_bytes < 32 or self.max_bytes > 4096:
            self.skipTest("Unsupported filesystem filename limit")

    def filename(self, *, unicode=False, excess=0):
        # Byte limits, not Python character counts: 🚀 consumes four UTF-8 bytes.
        marker = "🚀" if unicode else "a"
        suffix = ".pdf"
        padding = self.max_bytes + excess - len(os.fsencode(marker + suffix))
        self.assertGreater(padding, 0)
        name = marker + "x" * padding + suffix
        self.assertEqual(len(os.fsencode(name)), self.max_bytes + excess)
        return name

    def mocked_gate(self, stack):
        stack.enter_context(patch.object(gate, "CACHE_DB", self.root / "cache.sqlite3"))
        stack.enter_context(patch.object(gate, "SCAN_REQUEST_DB", self.root / "audit.sqlite3"))
        stack.enter_context(patch.object(gate, "intended_destination",
                                         return_value="com.brave.Browser"))
        stack.enter_context(patch.object(gate, "pdf_fallback_application", return_value=None))
        stack.enter_context(patch.object(gate, "record_scan_destination"))
        stack.enter_context(patch.object(gate, "verify_launch_target"))
        stack.enter_context(patch.object(gate, "verify_local_file_available"))
        stack.enter_context(patch.object(gate, "scan_engine_version", return_value=None))
        stack.enter_context(patch.object(gate, "read_signature_database_version",
                                         return_value=None))
        quarantine = stack.enter_context(patch.object(gate, "remove_quarantine"))
        launcher = stack.enter_context(patch.object(gate, "launch_clean_file"))
        def scan(command, **kwargs):
            self.assertEqual(command[0], "/scanner")
            self.assertEqual(command[-2], "--")
            return subprocess.CompletedProcess(command, 0, "file: OK", "")
        scanner = stack.enter_context(patch.object(gate.subprocess, "run", side_effect=scan))
        return scanner, launcher, quarantine

    def test_maximum_length_ascii_and_utf8_names_scan_and_open_unchanged(self):
        for index, unicode in enumerate((False, True)):
            with self.subTest(unicode=unicode):
                path = self.root / self.filename(unicode=unicode)
                content = b"%PDF-1.4\n% long-name test " + str(index).encode("ascii") + b"\n"
                path.write_bytes(content)
                self.assertEqual(path.name, path.resolve(strict=True).name)
                self.assertEqual(gate.validate_scan_request(path), path)
                self.assertEqual(gate.supported_request_path(path), path)
                with ExitStack() as stack:
                    scanner, launcher, quarantine = self.mocked_gate(stack)
                    clean = gate.scan_and_open(path, "/scanner")
                    cached = gate.scan_and_open(path, "/scanner")
                    self.assertEqual((clean.status, cached.status), ("clean", "clean"))
                    self.assertEqual((clean.from_cache, cached.from_cache), (False, True))
                    scanner.assert_called_once()
                    self.assertEqual(scanner.call_args.args[0][-1], str(path))
                    self.assertEqual(launcher.call_count, 2)
                    self.assertEqual([call.args[0] for call in launcher.call_args_list],
                                     [path, path])
                    self.assertEqual(quarantine.call_count, 2)
                self.assertEqual(path.read_bytes(), content)
                self.assertEqual(len(os.fsencode(path.name)), self.max_bytes)

    def test_maximum_length_selected_symlink_is_not_truncated(self):
        original = self.root / "target.pdf"
        original.write_bytes(b"%PDF-1.4\n% alias\n")
        alias = self.root / self.filename(unicode=True)
        alias.symlink_to(original)
        resolved, links = gate.symbolic_link_identity(alias)
        self.assertEqual(resolved, original)
        self.assertTrue(any(link[0] == str(alias) for link in links))
        with ExitStack() as stack:
            scanner, launcher, _ = self.mocked_gate(stack)
            self.assertEqual(gate.scan_and_open(alias, "/scanner").status, "clean")
            scanner.assert_called_once()
            self.assertEqual(scanner.call_args.args[0][-1], str(original))
            launcher.assert_called_once()
            self.assertEqual(launcher.call_args.args[0], original)

    def test_over_limit_ascii_and_utf8_names_fail_before_scanner_or_cache(self):
        for unicode in (False, True):
            with self.subTest(unicode=unicode):
                path = self.root / self.filename(unicode=unicode, excess=1)
                with self.assertRaises(OSError) as filesystem_failure:
                    path.write_bytes(b"%PDF-1.4\n")
                self.assertEqual(filesystem_failure.exception.errno, errno.ENAMETOOLONG)
                for admission in (gate.validate_scan_request, gate.supported_request_path):
                    with self.subTest(admission=admission.__name__):
                        with self.assertRaises((OSError, RuntimeError)) as failure:
                            admission(path)
                        safe = gate.safe_scan_failure(failure.exception)
                        self.assertNotIn(str(path), safe)
                        self.assertNotIn(path.name, safe)
                with patch.object(gate, "scan_slot") as queue, \
                        patch.object(gate, "cached_clean") as cache, \
                        patch.object(gate, "run_scan_command") as scanner, \
                        patch.object(gate, "remember_clean") as remember, \
                        patch.object(gate, "launch_clean_file") as launcher, \
                        patch.object(gate, "remove_quarantine") as quarantine:
                    with self.assertRaises((OSError, RuntimeError)) as failure:
                        gate.scan_and_open(path, "/scanner")
                    self.assertNotIn(path.name, gate.safe_scan_failure(failure.exception))
                for side_effect in (queue, cache, scanner, remember, launcher, quarantine):
                    side_effect.assert_not_called()
                self.assertFalse(path.exists())

    def test_over_limit_cli_batch_emits_only_sanitized_failure(self):
        over_limit = self.root / self.filename(excess=1)
        report = io.StringIO()
        with patch.object(gate, "watch_parent_lifetime"), \
                patch.object(gate, "scanner_path") as scanner_path, \
                patch.object(gate, "check_database") as database, \
                patch.object(gate, "scan_and_open") as scan, \
                redirect_stderr(report):
            result = gate.main([str(over_limit)])
        self.assertEqual(result, 1)
        self.assertIn("Scan request 1:", report.getvalue())
        self.assertNotIn(str(over_limit), report.getvalue())
        self.assertNotIn(over_limit.name, report.getvalue())
        scanner_path.assert_not_called()
        database.assert_not_called()
        scan.assert_not_called()


if __name__ == "__main__":
    unittest.main()
