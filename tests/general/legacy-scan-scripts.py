#!/usr/bin/env python3
"""Regression coverage for read-only preflight of installed scan entry points."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
DETECTOR = ROOT / "scripts/detect_existing_scan_scripts.py"
module_spec = importlib.util.spec_from_file_location("legacy_scan_script_detector", DETECTOR)
detector = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(detector)


class ExistingScanScriptsTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory(prefix="opener-legacy-scans-")
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.install_dir = self.root / "Library/Application Support/Studio/allow-and-open"

  def run_detector(self):
    return subprocess.run(
      [sys.executable, str(DETECTOR), str(self.install_dir)],
      capture_output=True, text=True, check=False,
    )

  def test_fresh_install_has_no_scripts_and_does_not_create_directory(self):
    self.assertEqual(detector.detect_existing_scan_scripts(self.install_dir), ())
    result = self.run_detector()
    self.assertEqual(result.returncode, 0)
    self.assertEqual(result.stdout.strip(), "No existing scan scripts detected.")
    self.assertFalse(self.install_dir.exists())

  def test_full_existing_install_detected_without_reading_or_mutating(self):
    self.install_dir.mkdir(parents=True)
    originals = {}
    for name in detector.SCAN_SCRIPTS:
      script = self.install_dir / name
      script.write_bytes(b"original user-customized contents\n")
      script.chmod(0o000)  # Detection needs metadata, not read/execute access.
      originals[name] = (script.stat().st_ino, script.stat().st_mtime_ns)
    other = self.install_dir / "target-app.txt"
    other.write_text("org.mozilla.firefox\n")
    original_other = (other.stat().st_ino, other.stat().st_mtime_ns)

    self.assertEqual(detector.detect_existing_scan_scripts(self.install_dir), detector.SCAN_SCRIPTS)
    result = self.run_detector()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(result.stdout.strip(), "Existing scan scripts detected: allow-and-open.sh, scan-and-open.py")
    for name, metadata in originals.items():
      script = self.install_dir / name
      self.assertEqual((script.stat().st_ino, script.stat().st_mtime_ns), metadata)
      self.assertEqual(script.stat().st_mode & 0o777, 0)
    self.assertEqual(other.read_text(), "org.mozilla.firefox\n")
    self.assertEqual((other.stat().st_ino, other.stat().st_mtime_ns), original_other)

  def test_partial_install_reports_only_present_script(self):
    self.install_dir.mkdir(parents=True)
    (self.install_dir / "scan-and-open.py").write_text("# historical script\n")
    self.assertEqual(detector.detect_existing_scan_scripts(self.install_dir), ("scan-and-open.py",))
    self.assertIn("Existing scan scripts detected: scan-and-open.py", self.run_detector().stdout)

  def test_unrelated_files_are_not_mistaken_for_scan_scripts(self):
    self.install_dir.mkdir(parents=True)
    (self.install_dir / "update-malware-signatures.sh").write_text("# not a scan entry point\n")
    (self.install_dir / "target-app.txt").write_text("custom-app\n")
    self.assertEqual(detector.detect_existing_scan_scripts(self.install_dir), ())

  def test_symlinked_script_or_directory_fails_closed_without_touching_target(self):
    outside = self.root / "outside.sh"
    outside.write_text("preserve me\n")
    self.install_dir.mkdir(parents=True)
    (self.install_dir / "allow-and-open.sh").symlink_to(outside)
    self.assertEqual(self.run_detector().returncode, 1)
    self.assertEqual(outside.read_text(), "preserve me\n")
    (self.install_dir / "allow-and-open.sh").unlink()
    self.install_dir.rmdir()
    self.install_dir.symlink_to(self.root, target_is_directory=True)
    self.assertEqual(self.run_detector().returncode, 1)
    self.assertEqual(outside.read_text(), "preserve me\n")

  def test_nonregular_entry_fails_closed(self):
    self.install_dir.mkdir(parents=True)
    (self.install_dir / "scan-and-open.py").mkdir()
    self.assertEqual(self.run_detector().returncode, 1)

  def test_installer_probes_before_any_installed_script_replacement(self):
    installer = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
    invocation = 'python3 "$script_dir/scripts/detect_existing_scan_scripts.py" "$install_dir"'
    self.assertIn(invocation, installer)
    self.assertLess(installer.index(invocation), installer.index('mkdir -p "$install_dir/signatures"'))
    self.assertLess(installer.index(invocation), installer.index('cp "$script_dir/allow-and-open.sh"'))
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    self.assertIn("PYTHONPATH=. python3 tests/general/legacy-scan-scripts.py -v", workflow)


if __name__ == "__main__":
  unittest.main()
