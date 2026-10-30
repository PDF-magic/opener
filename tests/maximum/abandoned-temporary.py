#!/usr/bin/env python3
"""opener-0541: reclaim abandoned Maximum temporary files without broad sweeps."""
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import maximum_temporary_output as cleanup


class AbandonedMaximumTemporaryTests(unittest.TestCase):
    def setUp(self):
        self.parent = tempfile.TemporaryDirectory(prefix="abandoned-output-tests-")
        self.addCleanup(self.parent.cleanup)
        self.root = Path(self.parent.name) / "owned-copies"
        patcher = patch.object(cleanup, "_PRIVATE_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def age(path):
        past = time.time() - cleanup._ABANDONED_AFTER_SECONDS - 120
        os.utime(path, (past, past), follow_symlinks=False)

    @staticmethod
    def abandon(lease):
        # Model a process restart that loses its in-memory lease registry.
        with cleanup._LOCK:
            cleanup._LEASES.pop(lease)

    def test_real_exited_process_is_reaped_on_next_stage(self):
        script = (
            "from pathlib import Path; import sys; "
            "import maximum_temporary_output as m; "
            "m._PRIVATE_ROOT = Path(sys.argv[1]); "
            "print(m.stage_maximum_temporary_pdf(b'%PDF-1.7\\ncopy').path)"
        )
        child = subprocess.run(
            [sys.executable, "-c", script, str(self.root)],
            cwd=Path(__file__).resolve().parent,
            capture_output=True, text=True, check=True,
        )
        old_file = Path(child.stdout.strip())
        self.assertTrue(old_file.is_file())
        self.age(old_file)
        self.age(old_file.parent)
        replacement = cleanup.stage_maximum_temporary_pdf(b"%PDF-1.7\nnew")
        try:
            self.assertFalse(old_file.exists())
            self.assertFalse(old_file.parent.exists())
            self.assertTrue(replacement.path.exists())
        finally:
            replacement.release()

    def test_live_creator_preserved_even_when_old(self):
        lease = cleanup.stage_maximum_temporary_pdf(b"%PDF-1.7\nkeep")
        self.abandon(lease)
        self.age(lease.path)
        self.age(lease.path.parent)
        # A live PID protects even a lease forgotten by the in-memory registry.
        self.assertEqual(cleanup.cleanup_abandoned_temporary_pdfs(), 0)
        self.assertTrue(lease.path.is_file())
        # The test deliberately changed its identity; do not bypass lease
        # checks in production merely to dispose of this synthetic fixture.
        lease.path.unlink()
        lease.path.parent.rmdir()

    def test_recent_orphan_is_preserved(self):
        lease = cleanup.stage_maximum_temporary_pdf(b"%PDF-1.7\nkeep")
        self.abandon(lease)
        with patch.object(cleanup.os, "kill", side_effect=ProcessLookupError):
            self.assertEqual(cleanup.cleanup_abandoned_temporary_pdfs(), 0)
        self.assertTrue(lease.path.is_file())

    def test_unknown_directory_entries_and_symlinks_survive(self):
        lease = cleanup.stage_maximum_temporary_pdf(b"%PDF-1.7\nkeep")
        self.abandon(lease)
        sentinel = lease.path.parent / "unrelated"
        sentinel.write_text("keep")
        self.age(lease.path)
        self.age(sentinel)
        self.age(lease.path.parent)
        protected = Path(self.parent.name) / "protected.pdf"
        protected.write_bytes(b"do not delete")
        alias = self.root / "pdf-magic-safe-copy-99999999-abcdefgh"
        alias.symlink_to(protected)
        with patch.object(cleanup.os, "kill", side_effect=ProcessLookupError):
            self.assertEqual(cleanup.cleanup_abandoned_temporary_pdfs(), 0)
        self.assertEqual(sentinel.read_text(), "keep")
        self.assertEqual(protected.read_bytes(), b"do not delete")
        self.assertTrue(alias.is_symlink())
        self.assertTrue(lease.path.is_file())

    def test_hardlinked_file_is_not_reaped(self):
        lease = cleanup.stage_maximum_temporary_pdf(b"%PDF-1.7\nkeep")
        self.abandon(lease)
        linked = Path(self.parent.name) / "another.pdf"
        os.link(lease.path, linked)
        self.age(lease.path)
        self.age(lease.path.parent)
        with patch.object(cleanup.os, "kill", side_effect=ProcessLookupError):
            self.assertEqual(cleanup.cleanup_abandoned_temporary_pdfs(), 0)
        self.assertTrue(linked.is_file())
        self.assertTrue(lease.path.is_file())

    def test_private_root_symlink_never_followed(self):
        protected = Path(self.parent.name) / "protected"
        protected.mkdir()
        sentinel = protected / "original.pdf"
        sentinel.write_bytes(b"keep")
        alias = Path(self.parent.name) / "alias"
        alias.symlink_to(protected, target_is_directory=True)
        with patch.object(cleanup, "_PRIVATE_ROOT", alias):
            with self.assertRaises(cleanup.MaximumTemporaryOutputError):
                cleanup.cleanup_abandoned_temporary_pdfs()
            with self.assertRaises(cleanup.MaximumTemporaryOutputError):
                cleanup.stage_maximum_temporary_pdf(b"%PDF-1.7\nblocked")
        self.assertEqual(sentinel.read_bytes(), b"keep")

    def test_private_root_permissions_and_no_unowned_sweep(self):
        lease = cleanup.stage_maximum_temporary_pdf(b"%PDF-1.7\nkeep")
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        outside = Path(self.parent.name) / "pdf-magic-safe-copy-99999999-abcdefgh"
        outside.mkdir(mode=0o700)
        fake = outside / ("safe-copy-" + "a" * 32 + ".pdf")
        fake.write_bytes(b"%PDF-1.7\nnot owned")
        self.age(fake)
        self.age(outside)
        with patch.object(cleanup.os, "kill", side_effect=ProcessLookupError):
            cleanup.cleanup_abandoned_temporary_pdfs()
        self.assertTrue(fake.is_file())
        lease.release()


if __name__ == "__main__":
    unittest.main()
