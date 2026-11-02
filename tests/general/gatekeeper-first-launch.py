#!/usr/bin/env python3
"""Portable fail-closed regression tests for actual macOS first launch."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_gatekeeper_first_launch.py"
spec = importlib.util.spec_from_file_location("first_launch_gatekeeper", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def result(code, stdout="", stderr=""):
  return subprocess.CompletedProcess([], code, stdout, stderr)


class GatekeeperFirstLaunchTests(unittest.TestCase):
  def test_disabled_missing_ambiguous_and_failed_status_are_blocked(self):
    cases = [
      result(0, "assessments disabled\n"), result(1, "assessments enabled\n"),
      result(0), result(0, "assessments enabled\nassessments enabled\n"),
      result(0, "assessments enabled, assessments disabled\n"),
    ]
    for status in cases:
      with self.subTest(status=status):
        with self.assertRaises(module.FirstLaunchError):
          module.gatekeeper_enabled(status)
    module.gatekeeper_enabled(result(0, "assessments enabled\n"))

  def test_only_explicit_notarized_developer_id_acceptance_passes(self):
    cases = [
      result(1, "", "PDFMagicOpener.app: rejected"),
      result(0, "", "PDFMagicOpener.app: accepted\nsource=Developer ID"),
      result(0, "", "PDFMagicOpener.app: accepted"),
      result(2, "", "usage: spctl"),
      result(0, "", "source=Notarized Developer ID"),
      result(0, "", "PDFMagicOpener.app: rejected\nsource=Notarized Developer ID"),
    ]
    for status in cases:
      with self.subTest(status=status):
        with self.assertRaises(module.FirstLaunchError):
          module.notarized_acceptance(status)
    module.notarized_acceptance(result(
      0, "", "PDFMagicOpener.app: accepted\nsource=Notarized Developer ID"))

  @mock.patch.object(module.subprocess, "run")
  def test_process_inventory_fails_closed(self, runner):
    runner.return_value = result(1)
    self.assertEqual(module.app_pids(), set())
    runner.return_value = result(0, "123\n456\n")
    self.assertEqual(module.app_pids(), {123, 456})
    for value in [result(0), result(2, "", "error"),
                  result(0, "bad-pid\n"), result(0, "1\n")]:
      runner.return_value = value
      with self.assertRaises(module.FirstLaunchError):
        module.app_pids()

  @mock.patch.object(module, "app_pids", return_value={412})
  @mock.patch.object(module.subprocess, "Popen")
  def test_preexisting_process_must_not_launch(self, popen, pids):
    with self.assertRaisesRegex(module.FirstLaunchError, "existing app"):
      module.confirm_fresh_launch(Path("/tmp/PDFMagicOpener.app"))
    popen.assert_not_called()

  @mock.patch.object(module, "app_pids", side_effect=[set(), {412}, {412}, {412}])
  @mock.patch.object(module.time, "sleep")
  @mock.patch.object(module.os, "kill")
  @mock.patch.object(module.subprocess, "Popen")
  def test_launch_services_must_start_and_keep_a_new_process(
      self, popen, kill, sleep, pids):
    child = popen.return_value
    child.poll.return_value = None
    child.communicate.return_value = (b"", b"")
    app = Path("/tmp/PDFMagicOpener.app")
    module.confirm_fresh_launch(app)
    self.assertEqual(popen.call_args.args[0],
                     ["/usr/bin/open", "-n", "-W", "-a", str(app)])
    sleep.assert_called_with(5)
    kill.assert_called_once_with(412, module.signal.SIGTERM)

  @mock.patch.object(module, "app_pids", side_effect=[set(), set()])
  @mock.patch.object(module.time, "sleep")
  @mock.patch.object(module.subprocess, "Popen")
  def test_failed_launch_does_not_count_as_pass(self, popen, sleep, pids):
    child = popen.return_value
    child.poll.side_effect = [None, 1, 1]
    child.communicate.return_value = (b"", b"")
    with self.assertRaises(module.FirstLaunchError):
      module.confirm_fresh_launch(Path("/tmp/PDFMagicOpener.app"))

  def test_linux_cannot_claim_a_real_mac_gatekeeper_test(self):
    if sys.platform != "darwin":
      with self.assertRaisesRegex(module.FirstLaunchError, "real macOS"):
        module.verify(Path("/tmp/PDFMagicOpener.app"), "ABCDEFGHIJ")


if __name__ == "__main__":
  unittest.main()
