#!/usr/bin/env python3
"""Offline regression contracts for the read-only ClamAV release watch."""

import importlib.util
import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "clamav_compatibility_watch", ROOT / "scripts/clamav_compatibility_watch.py")
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)


def release(tag, *, draft=False, prerelease=False):
  return {"tag_name": tag, "draft": draft, "prerelease": prerelease,
          "html_url": "https://github.com/Cisco-Talos/clamav/releases/tag/" + tag}


def inventory(*extra):
  return [release("clamav-1.4.6"), release("clamav-1.5.4"),
          release("clamav-1.3.2"), *extra]


class CompatibilityWatchTests(unittest.TestCase):
  def test_both_supported_branches_present_and_reviewed(self):
    self.assertEqual(watch.assess_releases(inventory()), [])
    self.assertEqual(watch.REVIEWED_RELEASES,
                     {"1.4": "clamav-1.4.6", "1.5": "clamav-1.5.4"})

  def test_patch_update_on_either_branch_requires_review(self):
    for tag in ("clamav-1.4.7", "clamav-1.5.5"):
      with self.subTest(tag=tag):
        result = watch.assess_releases(inventory(release(tag)))
        self.assertEqual(len(result), 1)
        self.assertIn(tag, result[0])

  def test_new_stable_branch_requires_review_but_prerelease_does_not(self):
    self.assertIn("clamav-1.6.0",
                  " ".join(watch.assess_releases(inventory(release("clamav-1.6.0")))))
    self.assertIn("clamav-2.0.0",
                  " ".join(watch.assess_releases(inventory(release("clamav-2.0.0")))))
    self.assertEqual(watch.assess_releases(inventory(
        release("clamav-1.6.0-rc", prerelease=True),
        release("clamav-1.5.5", draft=True))), [])

  def test_missing_branch_and_invalid_response_fail_closed(self):
    for value in ([], {}, "invalid", [release("clamav-1.5.4")],
                  [release("clamav-1.4.6")], inventory({"bad": True}),
                  inventory({**release("clamav-1.4.7"), "html_url": "https://evil.test"}),
                  inventory({"tag_name": "clamav-1.5.6", "draft": "false",
                             "prerelease": False})):
      with self.subTest(value=str(value)[:100]):
        with self.assertRaises(watch.CompatibilityWatchError):
          watch.assess_releases(value)

  def test_order_does_not_mask_newer_patch(self):
    self.assertIn("clamav-1.4.7", " ".join(
        watch.assess_releases([release("clamav-1.4.7"), *inventory()])))
    self.assertEqual(watch.assess_releases([
        release("clamav-1.4.5"), release("clamav-1.5.3"), *inventory()]), [])

  def test_network_error_is_sanitized_and_not_retried(self):
    with mock.patch.object(watch.urllib.request, "urlopen",
                           side_effect=OSError("/private/user/secret")) as opener:
      with self.assertRaisesRegex(watch.CompatibilityWatchError,
                                  "Could not verify upstream") as captured:
        watch.fetch_releases()
    opener.assert_called_once()
    self.assertNotIn("/private", str(captured.exception))

  def test_check_is_read_only_and_never_claims_compatibility(self):
    with mock.patch.object(watch, "fetch_releases", return_value=inventory()):
      with redirect_stdout(io.StringIO()) as output:
        self.assertEqual(watch.main(), 0)
    self.assertIn("not a compatibility", output.getvalue())
    with mock.patch.object(watch, "fetch_releases",
                           return_value=inventory(release("clamav-1.5.5"))):
      with redirect_stderr(io.StringIO()) as error:
        self.assertEqual(watch.main(), 1)
    self.assertIn("review required", error.getvalue())
    self.assertNotIn("/private", error.getvalue())

  def test_documentation_workflow_and_runtime_contract_remain_separate(self):
    guide = (ROOT / "docs/scanner/compatibility-watch.md").read_text()
    index = (ROOT / "docs/README.md").read_text()
    workflow = (ROOT / ".github/workflows/clamav-compatibility-watch.yml").read_text()
    runtime = (ROOT / "scan-and-open.py").read_text()
    installer = (ROOT / "scripts/verify_installed_clamav.py").read_text()
    for marker in ("clamav-1.4.6", "clamav-1.5.4", "48-hour",
                   "EICAR", "fail-closed", "signature", "FreshClam"):
      self.assertIn(marker, guide)
    self.assertIn("[ClamAV compatibility watch](scanner/compatibility-watch.md)", index)
    self.assertIn("cron:", workflow)
    self.assertIn("workflow_dispatch:", workflow)
    self.assertIn("pull_request:", workflow)
    self.assertIn("contents: read", workflow)
    self.assertNotIn("issues: write", workflow)
    self.assertIn("tests/clamav/compatibility-watch.py -v", workflow)
    self.assertIn("github.event_name == 'schedule'", workflow)
    self.assertIn("python3 scripts/clamav_compatibility_watch.py", workflow)
    self.assertIn(r"1\.(?:4|5)\.[0-9]+", runtime)
    self.assertIn(r"1\.(?:4|5)\.[0-9]+", installer)


if __name__ == "__main__":
  unittest.main()
