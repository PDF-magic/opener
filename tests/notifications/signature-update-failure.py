#!/usr/bin/env python3
"""opener-0892: actual updater failures produce private, best-effort macOS notices."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = "/opt/homebrew/bin/freshclam /usr/local/bin/freshclam /usr/local/clamav/bin/freshclam"


class SignatureUpdateFailureNotificationTests(unittest.TestCase):
  def setUp(self):
    temp = tempfile.TemporaryDirectory(prefix="signature-failure-notification-")
    self.addCleanup(temp.cleanup)
    self.root = Path(temp.name)
    self.home = self.root / "home"
    self.install = self.home / "Library/Application Support/Studio/allow-and-open"
    self.signatures = self.install / "signatures"
    self.signatures.mkdir(parents=True)
    (self.signatures / "main.cvd").write_text("original main definitions\n")
    (self.signatures / "daily.cld").write_text("original daily definitions\n")
    (self.signatures / "last-successful-update").write_text("1700000000\n")
    (self.install / "freshclam.conf").write_text("DatabaseMirror example.test\n")
    self.freshclam = self.root / "fake-freshclam"
    self.freshclam.write_text('#!/bin/sh\necho "private /Users/example/document.pdf" >&2\nexit "$FAKE_EXIT"\n')
    self.freshclam.chmod(0o700)
    self.notice = self.root / "fake-osascript"
    self.notificationLog = self.root / "notifications"
    self.notice.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$NOTIFICATION_LOG"\nexit "$NOTIFICATION_EXIT"\n')
    self.notice.chmod(0o700)

    source = (ROOT / "update-malware-signatures.sh").read_text()
    self.assertIn(CANDIDATES, source)
    self.assertIn('if [ "$(/usr/bin/uname -s)" = "Darwin" ]', source)
    self.assertIn("/usr/bin/osascript -e 'display notification", source)
    self.assertIn('record_failure "$status"', source)
    self.assertLess(source.index('record_failure "$status"'), source.index("notify_signature_update_failure\n    fi"))
    self.assertIn('if [ "$status" -ne 0 ]; then', source)
    # Replace external commands only inside a disposable script; production
    # always uses the fixed macOS utility path and no dynamic notification text.
    begin = source.index("# BEGIN staged database verification (opener-0386)")
    end = source.index("# END staged database verification (opener-0386)")
    end += len("# END staged database verification (opener-0386)")
    source = source[:begin] + source[end:]
    source = source.replace(CANDIDATES, str(self.freshclam))
    source = source.replace('$(/usr/bin/uname -s)', '$(printf Darwin)')
    source = source.replace("/usr/bin/osascript", str(self.notice))
    self.script = self.root / "updater.sh"
    self.script.write_text(source)

  def invoke(self, code, *, notifierExit=0):
    return subprocess.run(
      ["bash", str(self.script)], capture_output=True, text=True, timeout=20,
      env=dict(os.environ, HOME=str(self.home), FAKE_EXIT=str(code),
               NOTIFICATION_LOG=str(self.notificationLog),
               NOTIFICATION_EXIT=str(notifierExit)),
    )

  def notifications(self):
    return self.notificationLog.read_text().splitlines() if self.notificationLog.exists() else []

  def test_failed_update_delivers_only_fixed_private_alert(self):
    result = self.invoke(17)
    self.assertEqual(result.returncode, 17, result.stderr)
    self.assertEqual(len(self.notifications()), 1)
    notice = self.notifications()[0]
    self.assertIn("A malware signature update failed.", notice)
    self.assertIn("Definitions may be outdated; check Updates in PDF Magic Opener.", notice)
    self.assertIn('with title "PDF Magic Opener"', notice)
    for secret in (str(self.root), str(self.home), "/Users/example",
                   "private", "document.pdf", "freshclam-error"):
      self.assertNotIn(secret, notice)
    self.assertIn("freshclam-error", (self.signatures / "last-failed-update").read_text())
    self.assertEqual((self.signatures / "last-successful-update").read_text(), "1700000000\n")
    self.assertEqual((self.signatures / "main.cvd").read_text(), "original main definitions\n")

  def test_success_has_no_failure_notification(self):
    result = self.invoke(0)
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(self.notifications(), [])

  def test_os_notification_failure_cannot_change_updater_result(self):
    result = self.invoke(9, notifierExit=55)
    self.assertEqual(result.returncode, 9)
    self.assertEqual(len(self.notifications()), 1)
    self.assertIn("freshclam-error", (self.signatures / "last-failed-update").read_text())
    self.assertEqual((self.signatures / "last-successful-update").read_text(), "1700000000\n")

  def test_lock_contention_never_misreports_an_attempt(self):
    (self.install / ".signature-update-lock").mkdir()
    result = self.invoke(12)
    self.assertNotEqual(result.returncode, 0)
    self.assertEqual(self.notifications(), [])
    self.assertFalse((self.signatures / "last-failed-update").exists())

  def test_missing_updater_reports_failure_without_untrusted_output(self):
    self.freshclam.unlink()
    result = self.invoke(0)
    self.assertNotEqual(result.returncode, 0)
    self.assertEqual(len(self.notifications()), 1)
    self.assertIn("updater-unavailable", (self.signatures / "last-failed-update").read_text())
    self.assertNotIn("/Users/example", self.notifications()[0])

  def test_real_mac_notification_remains_best_effort_and_platform_scoped(self):
    source = (ROOT / "update-malware-signatures.sh").read_text()
    notifier = source.split("notify_signature_update_failure() {", 1)[1].split("\n}", 1)[0]
    self.assertIn('if [ "$(/usr/bin/uname -s)" = "Darwin" ] && [ -x /usr/bin/osascript ]; then', notifier)
    self.assertIn("</dev/null >/dev/null 2>&1 || :", notifier)
    self.assertNotIn("$failure_reason", notifier)
    self.assertNotIn("$signature_dir", notifier)
    self.assertNotIn("$status", notifier)
    self.assertNotIn("$HOME", notifier)
    self.assertNotIn("eval", notifier)
    self.assertIn("tests/notifications/signature-update-failure.py -v",
                  (ROOT / ".github/workflows/ci.yml").read_text())
    page = (ROOT / "PDFMagicOpenerApp/NotificationsSettingsView.swift").read_text()
    self.assertIn("separately installed signature updater can show a generic failure notification", page)
    self.assertIn("No notification permission is requested", page)


if __name__ == "__main__":
  unittest.main()
