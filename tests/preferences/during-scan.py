#!/usr/bin/env python3
"""Regress editing real presentation preferences during an in-flight scan."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.dont_write_bytecode = True
source = (Path(__file__).resolve().parents[2]s[2] / "scan-and-open.py")
spec = importlib.util.spec_from_file_location("scan_and_open", source)
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)


class PreferencesDuringScanTests(unittest.TestCase):
  def setUp(self):
    self.helper = os.environ.get("PREFERENCE_TEST_HELPER")
    if not self.helper:
      self.skipTest("Compile the native preference helper and set PREFERENCE_TEST_HELPER")
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.suite = "local.studio.pdf-magic-opener.active-scan-test." + uuid4().hex
    self.addCleanup(self.run_helper, "cleanup")
    self.run_helper("seed")
    self.document = (Path(self.temp.name) / "test.pdf").resolve()
    self.document.write_bytes(b"%PDF-1.4\nsynthetic document")
    self.original = self.document.read_bytes()
    cache = patch.object(opener, "CACHE_DB", Path(self.temp.name) / "clean-cache.sqlite3")
    cache.start()
    self.addCleanup(cache.stop)
    audit = patch.object(opener, "SCAN_REQUEST_DB",
                         Path(self.temp.name) / "scan-requests.sqlite3")
    audit.start()
    self.addCleanup(audit.stop)

  def run_helper(self, action):
    subprocess.run([self.helper, action, self.suite], check=True, timeout=15,
                   capture_output=True, text=True)

  def exercise_scan(self, infected):
    started = threading.Event()
    release = threading.Event()
    outcomes = []

    def scan(command, timeout):
      started.set()
      if not release.wait(20):
        raise RuntimeError("Synthetic scanner was never released")
      if infected:
        return subprocess.CompletedProcess(command, 1,
                                           "test.pdf: Eicar-Test-Signature FOUND", "")
      return subprocess.CompletedProcess(command, 0, "test.pdf: OK", "")

    def worker():
      try:
        outcomes.append(opener.scan_and_open(self.document, "/scanner"))
      except Exception as error:
        outcomes.append(error)

    with patch.object(opener, "intended_destination", return_value="com.brave.Browser"), \
         patch.object(opener, "pdf_fallback_application", return_value=None), \
         patch.object(opener, "verify_local_file_available"), \
         patch.object(opener, "verify_launch_target"), \
         patch.object(opener, "read_signature_database_version", return_value="test-db"), \
         patch.object(opener, "scan_engine_version", return_value="test-engine"), \
         patch.object(opener, "remove_quarantine") as quarantine, \
         patch.object(opener, "launch_clean_file") as launch, \
         patch.object(opener, "run_scan_command", side_effect=scan) as run_scan:
      thread = threading.Thread(target=worker, daemon=True)
      try:
        thread.start()
        self.assertTrue(started.wait(8), "Scanner did not start")
        self.assertTrue(thread.is_alive(), "Scan completed before preferences were edited")
        launch.assert_not_called()
        quarantine.assert_not_called()

        # Each action is a separate process, using the actual preference save
        # APIs called by the UI, while the ClamAV verdict is still pending.
        self.run_helper("edit")
        self.run_helper("verify")
        self.assertTrue(thread.is_alive(), "Editing preferences interrupted the scan")
        launch.assert_not_called()
        quarantine.assert_not_called()
      finally:
        release.set()
        if thread.ident is not None:
          thread.join(timeout=8)

      self.assertFalse(thread.is_alive(), "Scan did not finish after release")
      run_scan.assert_called_once()
      command = run_scan.call_args.args[0]
      self.assertEqual(command[0], "/scanner")
      self.assertIn("--alert-encrypted=yes", command)
      self.assertEqual(command[-2:], ["--", str(self.document)])
      self.assertEqual(self.document.read_bytes(), self.original)
      self.assertEqual(len(outcomes), 1)
      if infected:
        self.assertIsInstance(outcomes[0], RuntimeError)
        self.assertIn("Malware", str(outcomes[0]))
        quarantine.assert_not_called()
        launch.assert_not_called()
      else:
        self.assertIsInstance(outcomes[0], opener.CleanScanResult)
        self.assertEqual(outcomes[0].status, "clean")
        self.assertFalse(outcomes[0].from_cache)
        quarantine.assert_called_once()
        launch.assert_called_once()
    self.run_helper("verify")

  def test_preferences_change_does_not_skip_an_active_clean_scan(self):
    self.exercise_scan(infected=False)

  def test_preferences_change_cannot_allow_a_blocked_scan(self):
    self.exercise_scan(infected=True)


if __name__ == "__main__":
  unittest.main()
