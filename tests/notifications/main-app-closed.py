#!/usr/bin/env python3
"""Test notifications from the separate PDF opener after the preferences app quits.

The real system Notification Center is replaced only at the transport boundary:
CI must not alter notification authorization, users' settings or the scan gate.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
OPENER = ROOT / "brave-pdf-opener.swift"
PREFERENCES = ROOT / "PDFMagicOpenerApp" / "PDFMagicOpenerApp.swift"
WORKFLOW = ROOT / ".github/workflows/ci.yml"


class NotificationsWhileMainAppClosedTests(unittest.TestCase):
  def test_native_opener_owns_notification_delivery_independently(self):
    native = OPENER.read_text()
    preferences = PREFERENCES.read_text()
    self.assertIn("UNUserNotificationCenter.current()", native)
    self.assertIn("func deliverSuccessfulScanNotification(", native)
    self.assertIn("func deliverBlockedFileNotification(", native)
    self.assertIn("NativeScanNotificationTransport", native)
    self.assertIn("center.getNotificationSettings", native)
    self.assertIn("center.requestAuthorization(options: [.alert])", native)
    self.assertIn("center.add(request)", native)
    self.assertIn("self.pendingSuccessNotifications += 1", native)
    self.assertIn("self.pendingSuccessNotifications -= 1", native)
    self.assertIn("if self.pending.isEmpty && self.pendingSuccessNotifications == 0", native)
    self.assertIn("let blockedNotificationKind = BlockedFileNotificationPreference.notificationKind(", native)
    self.assertIn("SuccessfulScanNotificationPreference.shouldNotify(", native)
    self.assertIn("alert.runModal()", native)
    self.assertIn("process.arguments = [script.path, path]", native)
    self.assertIn("app.setActivationPolicy(.accessory)", native)
    self.assertNotIn("UNUserNotificationCenter", preferences)
    self.assertIn("The installed PDF opener handles open events independently", preferences)

  def test_ci_builds_and_executes_closed_app_lifecycle_regression(self):
    workflow = WORKFLOW.read_text()
    self.assertIn("tests/notifications/main-app-closed.py -v", workflow)
    self.assertIn("tests/notifications/main-app-closed.py --live -v", workflow)
    self.assertTrue((ROOT / "test-notifications-main-app-closed.swift").is_file())
    self.assertIn("Build SwiftUI application target without registering PDF handling", workflow)

  @unittest.skipUnless(sys.platform == "darwin" and "--live" in sys.argv,
                       "Requires a macOS runner with the built preferences app")
  def test_notifications_after_quitting_real_preferences_app(self):
    runner = Path(os.environ["RUNNER_TEMP"])
    binary = (runner / "PDFMagicOpenerDerived/Build/Products/Debug"
              / "PDFMagicOpener.app/Contents/MacOS/PDFMagicOpener")
    self.assertTrue(binary.is_file(), "Build the Settings target first")
    settings = subprocess.Popen([str(binary)], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    try:
      time.sleep(0.5)
      self.assertIsNone(settings.poll(), "Settings did not launch")
    finally:
      if settings.poll() is None:
        settings.terminate()
      try:
        settings.wait(timeout=12)
      except subprocess.TimeoutExpired:
        settings.kill()
        settings.wait(timeout=5)
    self.assertIsNotNone(settings.poll(), "Main application must be closed")

    # Build the original native PDF handler minus its executable entrypoint so
    # the test's own @main drives real delivery with an in-memory transport.
    source = OPENER.read_text()
    boundary = "@main\nstruct PDFMagicOpenerEntry {"
    self.assertEqual(source.count(boundary), 1)
    with tempfile.TemporaryDirectory(prefix="pdf-notification-closed-") as folder:
      isolated = Path(folder)
      native = isolated / "NativeNotificationOwner.swift"
      native.write_text(source.split(boundary, 1)[0])
      executable = isolated / "NotificationLifecycleTests"
      subprocess.run([
        "xcrun", "swiftc", "-parse-as-library", "-warnings-as-errors",
        str(native), str(ROOT / "scan-progress-view.swift"),
        str(ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift"),
        str(ROOT / "test-notifications-main-app-closed.swift"),
        "-o", str(executable),
      ], cwd=ROOT, check=True, timeout=120)
      subprocess.run([str(executable)], cwd=ROOT, check=True, timeout=30)


if __name__ == "__main__":
  if "--live" in sys.argv:
    sys.argv.remove("--live")
    # skipUnless was evaluated at import time before --live removal.
  unittest.main()
