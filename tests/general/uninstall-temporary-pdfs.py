#!/usr/bin/env python3
"""opener-0993: uninstallation removes only verified abandoned private PDFs."""
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import maximum_temporary_output as owned

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "uninstall_temporary_pdfs.py"
GUIDE = ROOT / "docs/uninstall-procedure.md"
CI = ROOT / ".github/workflows/ci.yml"
PDF = b"%PDF-1.7\nsynthetic generated test copy"


class UninstallTemporaryPDFTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="opener-0993-tests-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.private_root = self.base / "owned-copies"
        patcher = patch.object(owned, "_PRIVATE_ROOT", self.private_root)
        patcher.start()
        self.addCleanup(patcher.stop)
        spec = importlib.util.spec_from_file_location("uninstall_temp_test", SCRIPT)
        self.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cli)

    def stage(self):
        return owned.stage_maximum_temporary_pdf(PDF)

    @staticmethod
    def abandon(lease):
        # Simulates a crashed/restarted owner: the in-memory lease was lost.
        with owned._LOCK:
            owned._LEASES.pop(lease)

    def run_cli(self, arguments, *, tty=True, response="REMOVE"):
        stdout, stderr = StringIO(), StringIO()
        with patch.object(self.cli.sys.stdin, "isatty", return_value=tty), \
             patch("builtins.input", return_value=response) as confirm, \
             redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.cli.main(arguments)
        return status, stdout.getvalue(), stderr.getvalue(), confirm

    def test_no_argument_is_read_only_and_does_not_create_root(self):
        code, message, errors, confirm = self.run_cli([])
        self.assertEqual(code, 0)
        self.assertFalse(self.private_root.exists())
        self.assertIn("No temporary files changed", message)
        self.assertEqual(errors, "")
        confirm.assert_not_called()

    def test_removal_is_explicit_interactive_and_confirmed(self):
        lease = self.stage()
        self.abandon(lease)
        with patch.object(owned.os, "kill", side_effect=ProcessLookupError):
            for tty, answer in ((False, "REMOVE"), (True, "no")):
                code, _, errors, _ = self.run_cli(["--remove"], tty=tty, response=answer)
                self.assertEqual(code, 2)
                self.assertIn("refused", errors)
                self.assertTrue(lease.path.is_file())
            code, message, errors, confirm = self.run_cli(["--remove"])
        self.assertEqual(code, 0)
        self.assertIn("Removed 1 verified", message)
        self.assertEqual(errors, "")
        confirm.assert_called_once()
        self.assertFalse(lease.path.exists())
        self.assertFalse(lease.path.parent.exists())
        self.assertEqual(self.run_cli(["--remove"])[0], 0)

    def test_live_process_and_active_lease_remain_untouched(self):
        live = self.stage()
        orphan = self.stage()
        self.abandon(orphan)
        self.assertEqual(owned.cleanup_uninstall_temporary_pdfs(), 0)
        self.assertTrue(live.path.exists())
        self.assertTrue(orphan.path.exists())
        # Even an unexpectedly missing PID must not override an active lease.
        with patch.object(owned.os, "kill", side_effect=ProcessLookupError):
            self.assertEqual(owned.cleanup_uninstall_temporary_pdfs(), 1)
        self.assertTrue(live.path.is_file())
        live.release()

    def test_unknown_entries_and_other_temp_roots_are_preserved(self):
        abandoned = self.stage()
        self.abandon(abandoned)
        unexpected = abandoned.path.parent / "user-note.txt"
        unexpected.write_text("keep custom data", encoding="utf-8")
        separate = self.base / "user.pdf"
        separate.write_bytes(b"keep user selected PDF")
        other = self.base / "pdf-magic-safe-copy-99999999-abcdefgh"
        other.mkdir(mode=0o700)
        (other / abandoned.path.name).write_bytes(b"not owned")
        with patch.object(owned.os, "kill", side_effect=ProcessLookupError):
            self.assertEqual(owned.cleanup_uninstall_temporary_pdfs(), 0)
        self.assertEqual(unexpected.read_text(), "keep custom data")
        self.assertTrue(abandoned.path.exists())
        self.assertEqual(separate.read_bytes(), b"keep user selected PDF")
        self.assertEqual((other / abandoned.path.name).read_bytes(), b"not owned")

    def test_rejects_symlinked_root_and_substituted_directory(self):
        protected = self.base / "protected"
        protected.mkdir()
        sentinel = protected / "keep.pdf"
        sentinel.write_bytes(b"keep")
        self.private_root.symlink_to(protected, target_is_directory=True)
        with self.assertRaises(owned.MaximumTemporaryOutputError):
            owned.cleanup_uninstall_temporary_pdfs()
        self.assertEqual(sentinel.read_bytes(), b"keep")
        self.private_root.unlink()
        lease = self.stage()
        self.abandon(lease)
        moved = self.base / "moved-output"
        lease.path.parent.rename(moved)
        lease.path.parent.symlink_to(protected, target_is_directory=True)
        with patch.object(owned.os, "kill", side_effect=ProcessLookupError):
            self.assertEqual(owned.cleanup_uninstall_temporary_pdfs(), 0)
        self.assertEqual(sentinel.read_bytes(), b"keep")
        self.assertTrue((moved / lease.path.name).exists())

    def test_refuses_hardlinks_and_unowned_permissions(self):
        lease = self.stage()
        self.abandon(lease)
        external = self.base / "hardlink.pdf"
        os.link(lease.path, external)
        with patch.object(owned.os, "kill", side_effect=ProcessLookupError):
            self.assertEqual(owned.cleanup_uninstall_temporary_pdfs(), 0)
        self.assertEqual(external.read_bytes(), PDF)
        external.unlink()
        os.chmod(lease.path, 0o644)
        with patch.object(owned.os, "kill", side_effect=ProcessLookupError):
            self.assertEqual(owned.cleanup_uninstall_temporary_pdfs(), 0)
        self.assertTrue(lease.path.exists())
        os.chmod(self.private_root, 0o755)
        with self.assertRaises(owned.MaximumTemporaryOutputError):
            owned.cleanup_uninstall_temporary_pdfs()

    def test_regular_abandoned_reaper_still_requires_seven_days(self):
        lease = self.stage()
        self.abandon(lease)
        with patch.object(owned.os, "kill", side_effect=ProcessLookupError):
            self.assertEqual(owned.cleanup_abandoned_temporary_pdfs(), 0)
        self.assertTrue(lease.path.exists())

    def test_docs_ci_and_scanner_boundary(self):
        guide = GUIDE.read_text(encoding="utf-8")
        self.assertIn("python3 uninstall_temporary_pdfs.py --remove", guide)
        self.assertIn("viewer", guide)
        self.assertIn("unrecognized", guide)
        self.assertIn("user preferences", guide.lower())
        workflow = CI.read_text(encoding="utf-8")
        self.assertIn("PYTHONPATH=. python3 tests/general/uninstall-temporary-pdfs.py -v", workflow)
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("uninstall_temporary_pdfs", scanner)
        self.assertNotIn("cleanup_uninstall_temporary_pdfs", scanner)


if __name__ == "__main__":
    unittest.main()
