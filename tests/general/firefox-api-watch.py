#!/usr/bin/env python3
"""Hermetic Firefox WebExtension API watch regressions (opener-1165)."""

import io
import json
from pathlib import Path
import sys
import unittest
from urllib import parse
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import firefox_api_watch as watch


class FakeResponse:
  def __init__(self, content):
    self.content = content

  def __enter__(self):
    return self

  def __exit__(self, *_args):
    return False

  def read(self, maximum):
    return self.content[:maximum]


class FirefoxAPIWatchTests(unittest.TestCase):
  def test_inventory_covers_relevant_apis_and_manifest_keys(self):
    manifest = json.loads((ROOT / "extensions/webextension/manifest.json").read_text())
    gecko = json.loads((
      ROOT / "extensions/webextension/firefox/gecko.json").read_text())
    for key in ("action", "background", "host_permissions", "incognito",
                "manifest_version", "optional_permissions", "permissions"):
      self.assertIn(key, manifest)
      self.assertIn(f"webextensions/manifest/{key}.json", watch.REVIEWED)
    self.assertIn("gecko", gecko)
    self.assertIn("webextensions/manifest/browser_specific_settings.json",
                  watch.REVIEWED)
    for api in ("action", "downloads", "permissions"):
      self.assertIn(f"webextensions/api/{api}.json", watch.REVIEWED)
    self.assertEqual(len(watch.REVIEWED), 11)
    self.assertTrue(all(watch.SHA.fullmatch(value)
                        for value in watch.REVIEWED.values()))
    self.assertEqual(manifest["permissions"], [])
    self.assertEqual(manifest["host_permissions"], [])
    self.assertEqual(manifest["optional_permissions"], ["downloads"])
    self.assertEqual(gecko["gecko"]["strict_min_version"], "128.0")

  def test_network_query_is_bounded_and_scoped_to_official_api(self):
    path = "webextensions/api/downloads.json"
    pin = watch.REVIEWED[path]
    def opener(req, timeout):
      self.assertEqual(req.get_method(), "GET")
      self.assertEqual(timeout, 15)
      self.assertEqual(req.full_url.split("?", 1)[0], watch.API_URL)
      self.assertEqual(parse.parse_qs(parse.urlsplit(req.full_url).query), {
        "path": [path], "per_page": ["1"]})
      self.assertEqual(req.get_header("Authorization"), "Bearer fake-ci-token")
      return FakeResponse(json.dumps([{"sha": pin}]).encode("utf-8"))
    self.assertEqual(watch.latest_commit(
      path, opener=opener, token="fake-ci-token"), pin)

  def test_malformed_missing_and_oversized_responses_fail_closed(self):
    for payload in (b"", b"not json", b"{}", b"[]", b'[{"sha":"short"}]',
                    b'[{"sha":42}]', b'[{}]',
                    json.dumps([{"sha": "a" * 40}] * 2).encode(),
                    b"x" * (watch.MAX_RESPONSE_BYTES + 1)):
      with self.subTest(payload=payload[:30]):
        with self.assertRaises(watch.FirefoxAPIWatchError):
          watch.latest_commit(
            "webextensions/api/action.json",
            opener=lambda *_args, **_kwargs: FakeResponse(payload))
    with self.assertRaises(watch.FirefoxAPIWatchError):
      watch.latest_commit(
        "webextensions/api/action.json",
        opener=mock.Mock(side_effect=OSError("offline")))
    with self.assertRaises(watch.FirefoxAPIWatchError):
      watch.latest_commit("webextensions/api/not-approved.json")

  def test_unchanged_inventory_is_clean_and_queries_every_path(self):
    calls = []
    def unchanged(path):
      calls.append(path)
      return watch.REVIEWED[path]
    self.assertEqual(watch.check(latest=unchanged), 11)
    self.assertEqual(calls, list(watch.REVIEWED))

  def test_changed_and_unavailable_sources_block_even_if_others_pass(self):
    calls = []
    def changed(path):
      calls.append(path)
      if path.endswith("downloads.json"):
        return "f" * 40
      if path.endswith("permissions.json"):
        raise watch.FirefoxAPIWatchError("upstream unavailable")
      return watch.REVIEWED[path]
    with self.assertRaises(watch.FirefoxAPIWatchError) as error:
      watch.check(latest=changed)
    self.assertEqual(calls, list(watch.REVIEWED))
    self.assertIn("downloads.json", str(error.exception))
    self.assertIn("upstream unavailable", str(error.exception))

  def test_invalid_sha_is_not_mistaken_for_a_revision(self):
    with self.assertRaises(watch.FirefoxAPIWatchError):
      watch.check(latest=lambda _path: "unsafe\n::notice")
    with mock.patch.dict(watch.REVIEWED, {
        "webextensions/api/downloads.json": "not-a-pin"}):
      with self.assertRaises(watch.FirefoxAPIWatchError):
        watch.check(latest=lambda path: watch.REVIEWED[path])

  def test_workflow_offline_pr_and_authenticated_live_schedule(self):
    workflow = (ROOT / ".github/workflows/firefox-api-watch.yml").read_text()
    self.assertIn("pull_request:", workflow)
    self.assertIn("merge_group:", workflow)
    self.assertIn("push:", workflow)
    self.assertIn("schedule:", workflow)
    self.assertIn("workflow_dispatch:", workflow)
    self.assertIn("tests/general/firefox-api-watch.py -v", workflow)
    self.assertIn("github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'", workflow)
    self.assertIn("GITHUB_TOKEN:", workflow)
    self.assertIn("contents: read", workflow)
    self.assertNotIn("contents: write", workflow)
    self.assertNotIn("issues: write", workflow)
    self.assertIn(
      "tests/general/firefox-api-watch.py -v",
      (ROOT / ".github/workflows/ci.yml").read_text())
    docs = (ROOT / "docs/firefox-api-watch.md").read_text()
    self.assertIn("https://github.com/mdn/browser-compat-data", docs)
    self.assertIn("https://blog.mozilla.org/addons/", docs)
    self.assertIn("firefox-api-watch.md", (ROOT / "docs/README.md").read_text())


if __name__ == "__main__":
  unittest.main()
