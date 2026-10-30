#!/usr/bin/env python3
"""opener-0368: reject bundle symlinks escaping the selected .app boundary."""

from contextlib import nullcontext
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "bundle_symlink_scan_gate", ROOT / "scan-and-open.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

REJECTION = (
    "Application bundle contains a link outside the bundle; opening was stopped."
)


class BundleSymlinkContainmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="opener-bundle-links-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / "Example.app"
        self.contents = self.bundle / "Contents"
        self.contents.mkdir(parents=True)
        self.payload = self.contents / "a-document.txt"
        self.payload.write_bytes(b"Ordinary in-bundle contents")
        self.outside = self.root / "outside-document.txt"
        self.outside.write_bytes(b"Outside data is never a bundle member")

    def reject(self):
        with self.assertRaises(RuntimeError) as caught:
            gate.fingerprint(self.bundle)
        self.assertEqual(str(caught.exception), REJECTION)
        self.assertNotIn(str(self.root), str(caught.exception))

    def test_absolute_symlink_to_external_file_fails_closed(self):
        (self.contents / "external").symlink_to(self.outside)
        self.reject()

    def test_relative_parent_traversal_to_external_file_fails_closed(self):
        (self.contents / "external").symlink_to(
            Path("../../outside-document.txt")
        )
        self.reject()

    def test_external_directory_symlink_is_rejected_without_recursion(self):
        directory = self.root / "outside-directory"
        directory.mkdir()
        (directory / "secret").write_bytes(b"do not read")
        (self.contents / "outside-directory").symlink_to(
            directory, target_is_directory=True
        )
        self.reject()

    def test_internal_symlink_chain_that_ultimately_escapes_is_rejected(self):
        (self.contents / "a-inside-alias").symlink_to("z-outside-alias")
        (self.contents / "z-outside-alias").symlink_to(self.outside)
        self.reject()

    def test_unresolved_and_cyclic_symlinks_fail_closed(self):
        for kind in ("missing", "cycle"):
            with self.subTest(kind=kind):
                first = self.contents / "dangling"
                if kind == "missing":
                    first.symlink_to("does-not-exist")
                else:
                    second = self.contents / "loop"
                    first.symlink_to("loop")
                    second.symlink_to("dangling")
                self.reject()
                first.unlink()
                if kind == "cycle":
                    second.unlink()

    def test_all_links_are_validated_before_any_bundle_file_is_opened(self):
        (self.contents / "z-bad-link").symlink_to(self.outside)
        with patch.object(
            Path, "open", side_effect=AssertionError("No bundle bytes before preflight")
        ) as opened:
            self.reject()
        opened.assert_not_called()

    def test_safe_in_bundle_file_and_directory_aliases_still_hash(self):
        (self.contents / "safe-file").symlink_to("a-document.txt")
        target_dir = self.contents / "Internal"
        target_dir.mkdir()
        (target_dir / "data").write_bytes(b"safe internal directory")
        (self.contents / "safe-dir").symlink_to(
            "Internal", target_is_directory=True
        )
        before = gate.fingerprint(self.bundle)
        self.assertEqual(before, gate.fingerprint(self.bundle))
        self.assertEqual(len(before), 32)
        self.payload.write_bytes(b"changed ordinary in-bundle contents")
        self.assertNotEqual(before, gate.fingerprint(self.bundle))

    def test_bundle_scan_blocks_escape_before_cache_scanner_or_open(self):
        (self.contents / "z-escape").symlink_to(self.outside)
        with patch.object(gate, "scan_slot", return_value=nullcontext()), \
             patch.object(gate, "record_scan_destination"), \
             patch.object(gate, "intended_destination", return_value="system-default"), \
             patch.object(gate, "cached_clean") as cached, \
             patch.object(gate, "run_scan_command") as scanned, \
             patch.object(gate, "remember_clean") as saved, \
             patch.object(gate, "remove_quarantine") as quarantine, \
             patch.object(gate, "launch_clean_file") as opened:
            with self.assertRaisesRegex(RuntimeError, "Application bundle contains a link"):
                gate.scan_and_open(self.bundle, "/scanner")
        cached.assert_not_called()
        scanned.assert_not_called()
        saved.assert_not_called()
        quarantine.assert_not_called()
        opened.assert_not_called()

    def test_containment_runs_before_hashing_and_preserves_scan_invariants(self):
        source = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        preflight = source.index("target = entry.resolve(strict=True)")
        hashed = source.index("with entry.open('rb') as stream:")
        self.assertLess(preflight, hashed)
        self.assertIn("not target.is_relative_to(root)", source)
        self.assertIn("'--follow-file-symlinks=2', '--follow-dir-symlinks=2'", source)
        self.assertIn("verify_file_integrity(path, before, identity)", source)
        self.assertIn("if not cached_clean(cache_id):", source)
        self.assertIn("decision = decide_opening(detection)", source)


if __name__ == "__main__":
    unittest.main()
