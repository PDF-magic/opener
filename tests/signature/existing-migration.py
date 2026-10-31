#!/usr/bin/env python3
"""Hermetic migration and fail-closed regression coverage for opener-0941."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
  "signature_migration", ROOT / "scripts/migrate_signature_files.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class SignatureMigrationTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    self.old = self.root / "legacy"
    self.old.mkdir()
    self.new = self.root / "new"
    self.scanner = self.root / "fake-clamscan"
    self.scanner.write_text(
      "#!/usr/bin/env python3\n"
      "import os,sys\n"
      "directory=next(x[11:] for x in sys.argv if x.startswith('--database='))\n"
      "if os.environ.get('REJECT_SIGNATURES') or not os.path.exists(directory+'/main.cvd'):\n"
      "  sys.exit(2)\n"
      "print(sys.argv[-1]+': OK')\n")
    self.scanner.chmod(0o700)
    self.populate()

  def populate(self):
    (self.old / "main.cvd").write_bytes(b"ClamAV-VDB:" + b"m" * 501)
    (self.old / "daily.cld").write_bytes(b"ClamAV-VDB:" + b"d" * 501)
    (self.old / "custom.ndb").write_bytes(b"Example.Signature:0:*:abcdef\n")
    (self.old / "last-successful-update").write_text("9999999999\n")
    (self.old / "proxy-password.txt").write_text("do-not-read-or-copy\n")

  def migrate(self):
    return migration.migrate_signatures(self.old, self.new, self.scanner)

  def test_compatible_signatures_copy_without_forging_freshness(self):
    self.assertTrue(self.migrate())
    for name in ("main.cvd", "daily.cld", "custom.ndb"):
      self.assertEqual((self.old / name).read_bytes(), (self.new / name).read_bytes())
      self.assertEqual((self.new / name).stat().st_mode & 0o777, 0o600)
    self.assertFalse((self.new / "last-successful-update").exists())
    self.assertFalse((self.new / "proxy-password.txt").exists())
    self.assertTrue((self.old / "proxy-password.txt").exists())
    self.assertFalse(self.migrate())

  def test_existing_destination_is_never_overwritten(self):
    self.new.mkdir()
    (self.new / "main.cvd").write_bytes(b"user-owned-newer")
    (self.new / "custom.ndb").write_bytes(b"user customizations")
    self.assertFalse(self.migrate())
    self.assertEqual((self.new / "main.cvd").read_bytes(), b"user-owned-newer")
    self.assertEqual((self.new / "custom.ndb").read_bytes(), b"user customizations")

  def test_incomplete_ambiguous_and_unrecognized_databases_fail_closed(self):
    for action in ("missing", "ambiguous", "truncated"):
      with self.subTest(action=action):
        if action == "missing":
          (self.old / "daily.cld").unlink()
        elif action == "ambiguous":
          (self.old / "main.cld").write_bytes(b"ClamAV-VDB:" + b"m" * 501)
        else:
          (self.old / "main.cvd").write_bytes(b"ClamAV-VDB:partial")
        with self.assertRaises(migration.MigrationError):
          self.migrate()
        self.assertFalse(self.new.exists())
        self.assertEqual(list(self.root.glob(".signature-migration.*")), [])
        self.old.joinpath("main.cld").unlink(missing_ok=True)
        self.old.joinpath("main.cvd").write_bytes(b"ClamAV-VDB:" + b"m" * 501)
        self.old.joinpath("daily.cld").write_bytes(b"ClamAV-VDB:" + b"d" * 501)

  def test_symlinked_source_or_signature_is_never_followed(self):
    secret = self.root / "sensitive"
    secret.write_bytes(b"do not read")
    (self.old / "daily.cld").unlink()
    (self.old / "daily.cld").symlink_to(secret)
    with self.assertRaises(migration.MigrationError):
      self.migrate()
    self.assertEqual(secret.read_bytes(), b"do not read")
    self.assertFalse(self.new.exists())
    (self.old / "daily.cld").unlink()
    (self.old / "daily.cld").write_bytes(b"ClamAV-VDB:" + b"d" * 501)
    alias = self.root / "alias"
    alias.symlink_to(self.old, target_is_directory=True)
    with self.assertRaises(migration.MigrationError):
      migration.migrate_signatures(alias, self.new, self.scanner)

  def test_incompatible_scanner_does_not_publish_anything(self):
    original = self.scanner.read_text()
    self.scanner.write_text("#!/bin/sh\nexit 2\n")
    try:
      with self.assertRaisesRegex(migration.MigrationError, "ClamAV rejected"):
        self.migrate()
    finally:
      self.scanner.write_text(original)
    self.assertFalse(self.new.exists())
    self.assertTrue((self.old / "main.cvd").is_file())

  def test_scanner_absence_is_not_interpreted_as_compatibility(self):
    self.scanner.unlink()
    with self.assertRaises(migration.MigrationError):
      self.migrate()
    self.assertFalse(self.new.exists())

  def test_no_legacy_source_migrates_nothing(self):
    self.old.rename(self.root / "moved")
    with self.assertRaises(migration.MigrationError):
      self.migrate()
    self.assertFalse(self.new.exists())

  def test_ci_and_scanner_freshness_gate_stay_independent(self):
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    gate = (ROOT / "scan-and-open.py").read_text()
    self.assertIn("python3 tests/signature/existing-migration.py -v", ci)
    self.assertIn("MAX_DATABASE_AGE = 48 * 60 * 60", gate)
    self.assertIn("check_database()", gate)
    self.assertIn("last-successful-update", gate)


if __name__ == "__main__":
  unittest.main()
