#!/usr/bin/env python3
"""Check the real macOS native launch boundary without opening any application."""
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

def proof(path):
    info = path.lstat()
    return ":".join(str(x) for x in (info.st_dev, info.st_ino,
        stat.S_IFMT(info.st_mode), info.st_size, info.st_mtime_ns, info.st_ctime_ns))

class NativeIdentityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="native-identity-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.pdf = self.root / "download.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\\nsynthetic test only")
        self.launcher = sys.argv[1]

    def check(self, identity):
        return subprocess.run([self.launcher, "--expected-identity", identity,
                               "--check-local", str(self.pdf)],
                              capture_output=True, timeout=10).returncode

    def test_unchanged_file_and_cached_handoff(self):
        original = proof(self.pdf)
        self.assertEqual(self.check(original), 0)
        self.assertEqual(self.check(original), 0)

    def test_identical_bytes_replaced_inode_rejected(self):
        original = proof(self.pdf)
        backup = self.root / "old.pdf"
        self.pdf.rename(backup)
        self.pdf.write_bytes(backup.read_bytes())
        self.assertEqual(self.pdf.read_bytes(), backup.read_bytes())
        self.assertNotEqual(self.pdf.stat().st_ino, backup.stat().st_ino)
        self.assertNotEqual(self.check(original), 0)
        self.assertEqual(self.check(proof(self.pdf)), 0)

    def test_malformed_missing_and_symlinked_path_rejected(self):
        original = proof(self.pdf)
        self.assertNotEqual(self.check("not-a-valid-proof"), 0)
        self.assertNotEqual(self.check(original + ":unexpected"), 0)
        self.pdf.unlink()
        self.assertNotEqual(self.check(original), 0)
        target = self.root / "other.pdf"
        target.write_bytes(b"%PDF-1.4\\n")
        self.pdf.symlink_to(target)
        self.assertNotEqual(self.check(original), 0)

if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], "-v"])
