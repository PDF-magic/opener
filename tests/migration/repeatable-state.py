#!/usr/bin/env python3
"""opener-0949: interruption, repetition, and completion migration contracts."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts/migration_state.py"
spec = importlib.util.spec_from_file_location("migration_state", SOURCE)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class MigrationStateTests(unittest.TestCase):
  def setUp(self):
    temporary = tempfile.TemporaryDirectory(prefix="opener-state-")
    self.addCleanup(temporary.cleanup)
    self.home = Path(temporary.name)
    self.install = self.home / "Library/Application Support/Studio/allow-and-open"
    self.marker = self.install / migration.MARKER

  def test_fresh_read_only_detection_and_successful_completion(self):
    self.assertEqual(migration.status(self.home), "not_started")
    self.assertFalse(self.install.exists())
    attempt = migration.begin(self.home)
    self.assertEqual(len(attempt), 32)
    self.assertEqual(migration.status(self.home), "partial")
    self.assertIsNone(json.loads(self.marker.read_text())["last_completed"])
    migration.complete(self.home, attempt)
    self.assertEqual(migration.status(self.home), "complete")
    record = self.marker.read_bytes()
    migration.complete(self.home, attempt)
    self.assertEqual(self.marker.read_bytes(), record)
    self.assertEqual(self.marker.stat().st_mode & 0o777, 0o600)

  def test_interrupted_attempt_resumes_and_superseded_completion_fails(self):
    first = migration.begin(self.home)
    second = migration.begin(self.home)
    self.assertNotEqual(first, second)
    self.assertEqual(migration.status(self.home), "partial")
    with self.assertRaises(migration.MigrationStateError):
      migration.complete(self.home, first)
    migration.complete(self.home, second)
    self.assertEqual(migration.status(self.home), "complete")

  def test_reinstall_keeps_previous_success_until_next_completion(self):
    initial = migration.begin(self.home)
    migration.complete(self.home, initial)
    previous = json.loads(self.marker.read_text())["last_completed"]
    second = migration.begin(self.home)
    interrupted = json.loads(self.marker.read_text())
    self.assertEqual(interrupted["last_completed"], previous)
    self.assertEqual(migration.status(self.home), "partial")
    migration.complete(self.home, second)
    self.assertGreaterEqual(json.loads(self.marker.read_text())["last_completed"], previous)

  def test_unrelated_user_config_and_scanner_stamps_are_untouched(self):
    self.install.mkdir(parents=True)
    originals = {
      "target-app.txt": b"com.example.custom-pdf-viewer\n",
      "freshclam.conf": b"DatabaseMirror example.invalid\n# custom\n",
      "signatures/last-successful-update": b"1234567890\n",
      "custom-user-file": b"leave this alone",
    }
    for name, content in originals.items():
      file = self.install / name
      file.parent.mkdir(parents=True, exist_ok=True)
      file.write_bytes(content)
    first = migration.begin(self.home)
    second = migration.begin(self.home)
    migration.complete(self.home, second)
    migration.complete(self.home, second)
    self.assertEqual(migration.status(self.home), "complete")
    for name, content in originals.items():
      self.assertEqual((self.install / name).read_bytes(), content)
    with self.assertRaises(migration.MigrationStateError):
      migration.complete(self.home, first)

  def test_bad_markers_and_links_fail_closed_without_overwrite(self):
    self.install.mkdir(parents=True)
    outside = self.home / "unrelated"
    outside.write_bytes(b"original")
    self.marker.symlink_to(outside)
    with self.assertRaises(OSError):
      migration.status(self.home)
    with self.assertRaises(OSError):
      migration.begin(self.home)
    self.assertEqual(outside.read_bytes(), b"original")
    self.marker.unlink()
    for content in (b"not-json", b'{"version":2}', b"[]"):
      self.marker.write_bytes(content)
      with self.assertRaises(migration.MigrationStateError):
        migration.begin(self.home)
      self.assertEqual(self.marker.read_bytes(), content)
    self.marker.unlink()
    self.marker.write_bytes(b"unsafe")
    self.marker.chmod(0o666)
    with self.assertRaises(migration.MigrationStateError):
      migration.status(self.home)

  def test_directory_symlink_is_not_followed(self):
    victim = self.home / "outside"
    victim.mkdir()
    (self.home / "Library").symlink_to(victim, target_is_directory=True)
    with self.assertRaises(OSError):
      migration.begin(self.home)
    self.assertEqual(list(victim.iterdir()), [])

  def test_cli_reports_partial_and_complete_without_paths(self):
    def run(*args):
      return subprocess.run(
        [sys.executable, str(SOURCE), "--home", str(self.home), *args],
        capture_output=True, text=True, timeout=5,
      )
    self.assertEqual(run("status").stdout.strip(), "not_started")
    attempt = run("begin")
    self.assertEqual(attempt.returncode, 0, attempt.stderr)
    self.assertEqual(run("status").stdout.strip(), "partial")
    done = run("complete", attempt.stdout.strip())
    self.assertEqual(done.returncode, 0, done.stderr)
    self.assertEqual(run("status").stdout.strip(), "complete")
    self.assertNotIn(str(self.home), done.stdout)
    self.assertNotIn(str(self.home), done.stderr)

  def test_installer_only_records_completion_after_final_operations(self):
    installer = (ROOT / "install-allow-and-open.sh").read_text()
    begin = 'migration_attempt="$(python3 "$script_dir/scripts/migration_state.py" --home "$HOME" begin)"'
    finish = 'python3 "$script_dir/scripts/migration_state.py" --home "$HOME" complete "$migration_attempt"'
    self.assertIn(begin, installer)
    self.assertIn(finish, installer)
    self.assertLess(installer.index(begin), installer.index('brew install clamav'))
    self.assertLess(installer.index(finish), installer.index('echo "Installed local malware scanning'))
    self.assertGreater(installer.index(finish), installer.index('python3 "$install_dir/pdf-handler-status.py"'))
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    self.assertIn("python3 tests/migration/repeatable-state.py -v", ci)


if __name__ == "__main__":
  unittest.main()
