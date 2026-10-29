#!/usr/bin/env python3
"""opener-0384: FreshClam failures must be explicitly recorded and safe to display."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent
PATHS = "/opt/homebrew/bin/freshclam /usr/local/bin/freshclam /usr/local/clamav/bin/freshclam"


class UpdateFailureTests(unittest.TestCase):
  def setUp(self):
    temporary = tempfile.TemporaryDirectory(prefix="signature-failures-")
    self.addCleanup(temporary.cleanup)
    self.home = Path(temporary.name) / "home"
    self.stamps = self.home / "Library/Application Support/Studio/allow-and-open/signatures"
    self.stamps.mkdir(parents=True)
    self.fake = Path(temporary.name) / "fake-freshclam"
    self.fake.write_text('#!/bin/sh\necho "private path /somewhere" >&2\nexit "$FAKE_EXIT"\n')
    self.fake.chmod(0o700)
    self.script = Path(temporary.name) / "updater.sh"
    original = (ROOT / "update-malware-signatures.sh").read_text()
    self.assertIn(PATHS, original)
    # The failure-metadata tests use a fake FreshClam and bypass only the
    # separate opener-0386 validation block in their disposable script copy.
    first = original.index("# BEGIN staged database verification (opener-0386)")
    last = original.index("# END staged database verification (opener-0386)") + len("# END staged database verification (opener-0386)")
    original = original[:first] + original[last:]
    self.script.write_text(original.replace(PATHS, str(self.fake)))

  def invoke(self, code=0, missing=False):
    if missing and self.fake.exists():
      self.fake.unlink()
    return subprocess.run(["bash", str(self.script)],
                          env=dict(os.environ, HOME=str(self.home), FAKE_EXIT=str(code)),
                          capture_output=True, text=True, timeout=15)

  def read_failure(self):
    marker = self.stamps / "last-failed-update"
    self.assertTrue(marker.is_file())
    raw = marker.read_text()
    self.assertNotIn("private", raw)
    self.assertNotIn("/", raw)
    fields = raw.strip().split(" ")
    self.assertEqual(len(fields), 2)
    self.assertLessEqual(abs(int(time.time()) - int(fields[0])), 10)
    self.assertIn(fields[1], ("freshclam-error", "updater-unavailable"))
    return fields[1]

  def test_freshclam_failure_is_recorded_without_advancing_success(self):
    successful = self.stamps / "last-successful-update"
    successful.write_text("1700000000\n")
    result = self.invoke(17)
    self.assertEqual(result.returncode, 17)
    self.assertEqual(self.read_failure(), "freshclam-error")
    self.assertEqual(successful.read_text(), "1700000000\n")
    self.assertTrue((self.stamps / "last-attempted-update").is_file())

  def test_absent_updater_has_distinct_safe_failure_record(self):
    result = self.invoke(missing=True)
    self.assertNotEqual(result.returncode, 0)
    self.assertEqual(self.read_failure(), "updater-unavailable")
    self.assertFalse((self.stamps / "last-successful-update").exists())

  def test_success_does_not_erase_failure_history_or_fake_its_result(self):
    self.assertEqual(self.invoke(2).returncode, 2)
    before = (self.stamps / "last-failed-update").read_text()
    self.assertEqual(self.invoke(0).returncode, 0)
    self.assertEqual((self.stamps / "last-failed-update").read_text(), before)
    self.assertTrue((self.stamps / "last-successful-update").is_file())
    self.assertTrue((self.stamps / "last-attempted-update").is_file())

  def test_failure_is_never_raw_stderr_or_user_content(self):
    original = (ROOT / "update-malware-signatures.sh").read_text()
    self.assertIn('trap cleanup EXIT', original)
    self.assertIn('record_failure "$status"', original)
    self.assertIn('local status=$?', original)
    self.assertIn('printf \'%s %s\\n\'', original)
    self.assertNotIn("last-failed-update.new", original)
    self.assertIn('failure_reason="freshclam-error"', original)
    self.assertIn('failure_reason="updater-unavailable"', original)
    scanner = (ROOT / "scan-and-open.py").read_text()
    self.assertNotIn("last-failed-update", scanner)
    self.assertIn("MAX_DATABASE_AGE = 48 * 60 * 60", scanner)
    installer = (ROOT / "install-allow-and-open.sh").read_text()
    self.assertIn("'StartInterval': 14400", installer)
    self.assertIn("'RunAtLoad': True", installer)

  def test_display_and_ci_do_not_expose_freshclam_diagnostics(self):
    ui = (ROOT / "PDFMagicOpenerApp/UpdatesSettingsView.swift").read_text()
    model = (ROOT / "PDFMagicOpenerApp/SignatureUpdateStatus.swift").read_text()
    for term in ('"Signature update failure recorded"', '"Last failed update"',
                 'accessibilityIdentifier("signatureUpdateFailure")',
                 "signatureStatus.failureExplanation", "signatureStatus.hasUnresolvedFailure"):
      self.assertIn(term, ui)
    for term in ('"last-failed-update"', "updater-unavailable",
                 "freshclam-error", "O_NOFOLLOW", "S_IFREG", "hasUnresolvedFailure"):
      self.assertIn(term, model)
    self.assertNotIn("Process(", model)
    self.assertNotIn("URLSession", model)
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    self.assertIn("python3 test-signature-update-failures.py -v", ci)
    self.assertIn("test-signature-update-failures.swift", ci)


if __name__ == "__main__":
  unittest.main()
