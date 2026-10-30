#!/usr/bin/env python3
"""opener-0325: clean only owned temporary Maximum PDFs, never arbitrary files."""
from concurrent.futures import ThreadPoolExecutor
import os
import re
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import maximum_temporary_output as cleanup


class MaximumTemporaryOutputTests(unittest.TestCase):
    def setUp(self):
        self.parent = tempfile.TemporaryDirectory(prefix="maximum-cleanup-tests-")
        self.addCleanup(self.parent.cleanup)
        self.created = []
        root_patcher = patch.object(cleanup, "_PRIVATE_ROOT",
                                    Path(self.parent.name) / "owned-copies")
        root_patcher.start()
        self.addCleanup(root_patcher.stop)
        original = tempfile.mkdtemp

        def create(*, prefix=None, **kwargs):
            kwargs.setdefault("dir", self.parent.name)
            path = Path(original(prefix=prefix, **kwargs))
            self.created.append(path)
            return str(path)

        patcher = patch.object(cleanup.tempfile, "mkdtemp", side_effect=create)
        patcher.start()
        self.addCleanup(patcher.stop)

    def stage(self, contents=b"%PDF-1.7\nsafe generated content"):
        return cleanup.stage_maximum_temporary_pdf(contents)

    def test_private_exclusive_output_and_explicit_idempotent_release(self):
        lease = self.stage()
        self.assertEqual(lease.path.read_bytes(), b"%PDF-1.7\nsafe generated content")
        self.assertRegex(lease.path.name, r"^safe-copy-[0-9a-f]{32}\.pdf$")
        self.assertEqual(stat.S_IMODE(lease.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(lease.path.parent.stat().st_mode), 0o700)
        self.assertFalse(lease.released)
        lease.release()
        self.assertTrue(lease.released)
        self.assertFalse(lease.path.exists())
        self.assertFalse(lease.path.parent.exists())
        lease.release()

    def test_filename_uses_128_bits_of_unpredictable_randomness(self):
        leases = [self.stage() for _ in range(12)]
        try:
            names = [lease.path.name for lease in leases]
            self.assertEqual(len(set(names)), len(names))
            self.assertTrue(all(re.fullmatch(r"safe-copy-[0-9a-f]{32}\.pdf", name)
                                for name in names))
            with patch.object(cleanup.secrets, "token_hex",
                              return_value="a" * 32) as random_token:
                deterministic = self.stage()
            random_token.assert_called_once_with(16)
            self.assertEqual(deterministic.path.name, "safe-copy-" + "a" * 32 + ".pdf")
            deterministic.release()
        finally:
            for lease in leases:
                lease.release()

    def test_success_is_not_prematurely_deleted_and_context_failure_is_cleaned(self):
        keep = self.stage()
        self.assertTrue(keep.path.is_file())
        with self.assertRaisesRegex(RuntimeError, "simulated scan failure"):
            with self.stage() as staged:
                self.assertTrue(staged.path.is_file())
                raise RuntimeError("simulated scan failure")
        self.assertTrue(keep.path.is_file())
        keep.release()

    def test_concurrent_outputs_have_independent_cleanup(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            leases = list(pool.map(lambda _: self.stage(), range(8)))
        self.assertEqual(len({x.path for x in leases}), 8)
        for index, lease in enumerate(leases):
            if index % 2 == 0:
                lease.release()
        self.assertTrue(all(lease.released == (i % 2 == 0)
                            for i, lease in enumerate(leases)))
        self.assertTrue(all(lease.path.exists() for i, lease in enumerate(leases)
                            if i % 2 == 1))
        for lease in leases:
            lease.release()

    def test_untrusted_output_values_never_create_temp_files(self):
        for value in (None, "fake", b"", bytearray(b"%PDF-1.7\n"),
                      b"not PDF", b"%PDF-" + b"X" * cleanup.MAX_TEMP_PDF_BYTES):
            with self.subTest(kind=type(value).__name__):
                with self.assertRaises(cleanup.MaximumTemporaryOutputError):
                    cleanup.stage_maximum_temporary_pdf(value)
        self.assertEqual(self.created, [])

    def test_failed_write_unlinks_partial_file_and_directory(self):
        with patch.object(cleanup.os, "fsync",
                          side_effect=OSError("private-user-source.pdf")):
            with self.assertRaises(cleanup.MaximumTemporaryOutputError) as caught:
                self.stage()
        self.assertEqual(str(caught.exception), cleanup.BLOCK_MESSAGE)
        self.assertEqual(len(self.created), 1)
        self.assertFalse(self.created[0].exists())

    def test_verify_rejects_file_link_and_inode_substitution(self):
        lease = self.stage()
        lease.verify()
        protected = Path(self.parent.name) / "protected.pdf"
        protected.write_bytes(b"keep original bytes")
        lease.path.unlink()
        lease.path.symlink_to(protected)
        with self.assertRaises(cleanup.MaximumTemporaryOutputError) as caught:
            lease.verify()
        self.assertEqual(str(caught.exception), cleanup.BLOCK_MESSAGE)
        self.assertEqual(protected.read_bytes(), b"keep original bytes")
        lease.path.unlink()
        lease.path.parent.rmdir()

    def test_verify_rejects_directory_link_and_hardlinked_output(self):
        lease = self.stage()
        protected = Path(self.parent.name) / "protected"
        protected.mkdir()
        old = lease.path.parent.with_name(lease.path.parent.name + "-old")
        lease.path.parent.rename(old)
        lease.path.parent.symlink_to(protected, target_is_directory=True)
        with self.assertRaises(cleanup.MaximumTemporaryOutputError):
            lease.verify()
        lease.path.parent.unlink()
        old.rename(lease.path.parent)
        duplicate = Path(self.parent.name) / "linked.pdf"
        os.link(lease.path, duplicate)
        try:
            with self.assertRaises(cleanup.MaximumTemporaryOutputError):
                lease.verify()
        finally:
            duplicate.unlink()
        # Even after removing the extra hard link, inode ctime has changed:
        # the original lease must not accept it as the initial file.
        with self.assertRaises(cleanup.MaximumTemporaryOutputError):
            lease.verify()

    def test_file_symlink_substitution_does_not_follow_or_delete_target(self):
        protected = Path(self.parent.name) / "protected.pdf"
        protected.write_bytes(b"do not remove")
        lease = self.stage()
        lease.path.unlink()
        lease.path.symlink_to(protected)
        with self.assertRaises(cleanup.MaximumTemporaryOutputError):
            lease.release()
        self.assertFalse(lease.released)
        self.assertEqual(protected.read_bytes(), b"do not remove")
        self.assertTrue(lease.path.is_symlink())
        lease.path.unlink()
        lease.path.parent.rmdir()

    def test_file_inode_replacement_does_not_delete_new_file(self):
        lease = self.stage()
        lease.path.unlink()
        lease.path.write_bytes(b"replaced by another program")
        os.chmod(lease.path, 0o600)
        with self.assertRaises(cleanup.MaximumTemporaryOutputError):
            lease.release()
        self.assertEqual(lease.path.read_bytes(), b"replaced by another program")
        lease.path.unlink()
        lease.path.parent.rmdir()

    def test_directory_symlink_swap_refuses_to_follow_target(self):
        protected = Path(self.parent.name) / "protected"
        protected.mkdir()
        sentinel = protected / "keep.txt"
        sentinel.write_text("keep")
        lease = self.stage()
        original = lease.path.parent
        renamed = original.with_name(original.name + "-old")
        original.rename(renamed)
        original.symlink_to(protected, target_is_directory=True)
        with self.assertRaises(cleanup.MaximumTemporaryOutputError):
            lease.release()
        self.assertEqual(sentinel.read_text(), "keep")
        self.assertTrue(original.is_symlink())
        original.unlink()
        renamed.rename(original)
        lease.release()
        self.assertTrue(sentinel.exists())

    def test_extra_unknown_file_is_never_recursively_deleted(self):
        lease = self.stage()
        unrelated = lease.path.parent / "unrelated.txt"
        unrelated.write_text("must stay")
        with self.assertRaises(cleanup.MaximumTemporaryOutputError):
            lease.release()
        self.assertEqual(unrelated.read_text(), "must stay")
        self.assertFalse(lease.path.exists())
        unrelated.unlink()
        lease.path.parent.rmdir()

    def test_forged_lease_cannot_delete_user_supplied_file(self):
        protected = Path(self.parent.name) / "protected.pdf"
        protected.write_bytes(b"original user bytes")
        fake = cleanup.MaximumTemporaryOutput(protected)
        with self.assertRaises(cleanup.MaximumTemporaryOutputError):
            fake.release()
        self.assertEqual(protected.read_bytes(), b"original user bytes")
        with self.assertRaises(cleanup.MaximumTemporaryOutputError):
            cleanup.MaximumTemporaryOutput(Path(self.parent.name) / "fake.pdf").release()

    def test_active_scanner_and_profile_settings_unchanged(self):
        code = (Path(__file__).resolve().parents[2] / "scan-and-open.py").read_text()
        self.assertNotIn("maximum_temporary_output", code)
        self.assertIn("if not cached_clean(cache_id):", code)
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)


if __name__ == "__main__":
    unittest.main()
