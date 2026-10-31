#!/usr/bin/env python3
"""Descriptor-pinned input regression coverage (opener-0833)."""

import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("descriptor_scan_gate", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class DescriptorInputTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="descriptor-scan-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.pdf = self.root / "selected.pdf"
        self.content = b"%PDF-1.4\noriginal, unchanged bytes"
        self.pdf.write_bytes(self.content)

    def test_hash_uses_open_descriptor_metadata_and_closes_it(self):
        real_fstat = os.fstat
        with patch.object(gate.os, "fstat", wraps=real_fstat) as fstat:
            digest = gate.fingerprint(self.pdf)
        expected = hashlib.sha256(
            b"file-v1\0bytes\0" + str(len(self.content)).encode("ascii")
            + b"\0" + self.content
        ).digest()
        self.assertEqual(digest, expected)
        self.assertGreaterEqual(fstat.call_count, 1)
        fd = fstat.call_args.args[0]
        with self.assertRaises(OSError):
            real_fstat(fd)

    def test_substituted_symlink_is_never_followed_during_open(self):
        if not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("This platform lacks O_NOFOLLOW")
        outside = self.root / "untouched-other-file.pdf"
        outside.write_bytes(b"outside bytes")
        backup = self.root / "original.pdf"
        real_open = os.open
        seen_flags = []

        def substitute_before_open(path, flags, *args, **kwargs):
            if Path(path) == self.pdf:
                self.pdf.rename(backup)
                self.pdf.symlink_to(outside)
                seen_flags.append(flags)
            return real_open(path, flags, *args, **kwargs)

        with patch.object(gate.os, "open", side_effect=substitute_before_open):
            with self.assertRaises(RuntimeError) as failure:
                gate.fingerprint(self.pdf)
        self.assertEqual(str(failure.exception), gate.UNREADABLE_SCAN_INPUT_MESSAGE)
        self.assertTrue(seen_flags[0] & os.O_NOFOLLOW)
        self.assertEqual(outside.read_bytes(), b"outside bytes")

    def test_descriptor_closes_when_stream_creation_fails(self):
        real_open = os.open
        opened = []

        def record_open(path, flags, *args, **kwargs):
            fd = real_open(path, flags, *args, **kwargs)
            opened.append(fd)
            return fd

        with patch.object(gate.os, "open", side_effect=record_open), \
                patch.object(gate.os, "fdopen", side_effect=OSError("private path")):
            with self.assertRaises(RuntimeError) as failure:
                gate.fingerprint(self.pdf)
        self.assertEqual(str(failure.exception), gate.UNREADABLE_SCAN_INPUT_MESSAGE)
        self.assertNotIn(str(self.pdf), str(failure.exception))
        self.assertEqual(len(opened), 1)
        with self.assertRaises(OSError):
            os.fstat(opened[0])


if __name__ == "__main__":
    unittest.main()
