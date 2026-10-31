#!/usr/bin/env python3
"""opener-0837: cleanup cannot delete arbitrary files after pathname swaps.

The only files used are synthetic test fixtures in a disposable private root.
No real scanner, document, browser profile, configuration, or delete sweep runs.
"""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import maximum_temporary_output as cleanup

PDF = b"%PDF-1.7\nprivate generated fixture\n"


class ArbitraryFileDeletionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="opener-0837-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "private-owned-root"
        override = patch.object(cleanup, "_PRIVATE_ROOT", self.root)
        override.start()
        self.addCleanup(override.stop)

    def stage(self):
        return cleanup.stage_maximum_temporary_pdf(PDF)

    def test_forged_lease_and_unowned_file_cannot_be_deleted(self):
        original = self.base / "user-selected.pdf"
        original.write_bytes(b"private user document")
        forged = cleanup.MaximumTemporaryOutput(original)
        with self.assertRaises(cleanup.MaximumTemporaryOutputError):
            forged.release()
        self.assertEqual(original.read_bytes(), b"private user document")
        self.assertTrue(original.is_file())

    def test_failed_staging_does_not_delete_file_in_swapped_directory(self):
        """Reproduce a same-named foreign file installed after identity check."""
        true_stat = os.stat
        swapped = []
        unrelated = self.base / "important-user-document.pdf"
        unrelated.write_bytes(b"never remove")
        def replace_directory_during_stat(path, *args, **kwargs):
            recorded = true_stat(path, *args, **kwargs)
            name = str(path)
            if (not swapped and "safe-copy-" in name and name.endswith(".pdf") and
                    kwargs.get("follow_symlinks") is False):
                directories = list(self.root.glob("pdf-magic-safe-copy-*"))
                if len(directories) == 1:
                    owned = directories[0]
                    parked = self.base / "parked-original-stage"
                    owned.rename(parked)
                    owned.mkdir(mode=0o700)
                    foreign = owned / (Path(name).name)
                    foreign.write_bytes(b"foreign file, not owned by PDF Magic")
                    os.chmod(foreign, 0o600)
                    swapped.append(foreign)
            return recorded

        with patch.object(cleanup.os, "fsync", side_effect=OSError("test failure")), \\
                patch.object(cleanup.os, "stat",
                             side_effect=replace_directory_during_stat), \\
                self.assertRaises(cleanup.MaximumTemporaryOutputError):
            self.stage()
        self.assertEqual(len(swapped), 1, "race injection must actually execute")
        self.assertEqual(swapped[0].read_bytes(), b"foreign file, not owned by PDF Magic")
        self.assertEqual(unrelated.read_bytes(), b"never remove")

    def test_release_pins_directory_against_replacement(self):
        lease = self.stage()
        original = lease.path.parent
        parked = self.base / "parked-release-directory"
        target = self.base / "unrelated.pdf"
        target.write_bytes(b"preserve user content")
        true_stat = os.stat
        swapped = []
        def replace_directory(path, *args, **kwargs):
            result = true_stat(path, *args, **kwargs)
            if (not swapped and str(path) == lease.path.name and
                    kwargs.get("dir_fd") is not None and
                    kwargs.get("follow_symlinks") is False):
                original.rename(parked)
                original.mkdir(mode=0o700)
                swapped.append(True)
            return result

        with patch.object(cleanup.os, "stat", side_effect=replace_directory):
            with self.assertRaises(cleanup.MaximumTemporaryOutputError):
                lease.release()
        self.assertTrue(swapped)
        self.assertTrue(original.is_dir(), "foreign replacement directory must survive")
        self.assertEqual(target.read_bytes(), b"preserve user content")

    def test_normal_owned_cleanup_still_succeeds_and_unknown_content_survives(self):
        lease = self.stage()
        owned = lease.path
        lease.verify()
        lease.release()
        self.assertFalse(owned.exists())
        self.assertFalse(owned.parent.exists())

        another = self.stage()
        unknown = another.path.parent / "important.txt"
        unknown.write_bytes(b"keep unrelated entry")
        with self.assertRaises(cleanup.MaximumTemporaryOutputError):
            another.release()
        self.assertEqual(unknown.read_bytes(), b"keep unrelated entry")
        self.assertFalse(another.path.exists())


if __name__ == "__main__":
    unittest.main()
