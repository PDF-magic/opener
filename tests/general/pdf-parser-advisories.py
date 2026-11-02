#!/usr/bin/env python3
"""Offline parser advisory monitoring regression suite (opener-1162)."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import pdf_parser_advisory_watch as watch


class FakeResponse:
  def __init__(self, body):
    self.body = body

  def __enter__(self):
    return self

  def __exit__(self, *_):
    return False

  def read(self, count):
    return self.body[:count]


class ParserAdvisoryTests(unittest.TestCase):
  def test_inventory_includes_current_and_legacy_pypdf_and_pymupdf(self):
    with mock.patch.object(watch.dependencies, "pins", return_value=(
        {("pypdf", "6.21.4")}, {("pypdf", "5.9.0"), ("pymupdf", "2.0")})):
      self.assertEqual(watch.inventory(), [
        ("pymupdf", "2.0", False), ("pypdf", "5.9.0", False),
        ("pypdf", "6.21.4", True)])

  def test_missing_reviewed_parser_version_fails_closed(self):
    with mock.patch.object(watch.dependencies, "pins", return_value=(
        {("pypdf", "6.21.4")}, {("pypdf", "5.9.0")})):
      with self.assertRaises(watch.AdvisoryWatchError):
        watch.inventory()

  def test_query_uses_exact_pypi_version_and_bounded_json(self):
    def opener(req, timeout):
      self.assertEqual(req.full_url, "https://api.osv.dev/v1/query")
      self.assertEqual(timeout, 15)
      self.assertEqual(json.loads(req.data), {
        "package": {"ecosystem": "PyPI", "name": "pypdf"},
        "version": "6.21.4"})
      return FakeResponse(b'{"vulns":[{"id":"GHSA-abcd-1234-5678"}]}')
    self.assertEqual(watch.query_osv("pypdf", "6.21.4", opener=opener),
                     (["GHSA-abcd-1234-5678"], None))

  def test_malformed_or_unavailable_feed_is_not_clean(self):
    for body in (b'garbage', b'[]', b'{"vulns":null}',
                 b'{"vulns":[{"id":"bad\nline"}]}',
                 b'{"next_page_token":42}', b'X' * (watch.MAX_RESPONSE_BYTES + 1)):
      with self.subTest(body=body[:30]), self.assertRaises(watch.AdvisoryWatchError):
        watch.query_osv("pypdf", "6.21.4", opener=lambda *_args, **_kwargs: FakeResponse(body))
    with self.assertRaises(watch.AdvisoryWatchError):
      watch.query_osv("pypdf", "6.21.4", opener=mock.Mock(side_effect=OSError("network")))

  def test_all_pages_are_read_before_reporting_clean(self):
    calls = []
    def query(name, version, token):
      calls.append(token)
      return (["CVE-2026-1234"], "next") if token is None else (["GHSA-abcd-1234-5678"], None)
    self.assertEqual(watch.advisories("pypdf", "6.21.4", query=query),
                     ["CVE-2026-1234", "GHSA-abcd-1234-5678"])
    self.assertEqual(calls, [None, "next"])
    with self.assertRaises(watch.AdvisoryWatchError):
      watch.advisories("pypdf", "6.21.4", query=lambda *_: ([], "same"))

  def test_current_advisory_blocks_but_legacy_is_reported(self):
    inventory = [("pypdf", "5.9.0", False), ("pypdf", "6.21.4", True)]
    def query(name, version):
      return ["GHSA-aaaa-bbbb-cccc"] if version == "5.9.0" else []
    with redirect_stdout(io.StringIO()) as output:
      watch.check(inventory, query=query)
    self.assertIn("legacy CI-only parser", output.getvalue())
    self.assertIn("GHSA-aaaa-bbbb-cccc", output.getvalue())
    with self.assertRaises(watch.AdvisoryWatchError):
      watch.check(inventory, query=lambda *_: ["CVE-2026-1234"])

  def test_summary_includes_only_validated_identifiers(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / "summary.md"
      with mock.patch.dict("os.environ", {"GITHUB_STEP_SUMMARY": str(path)}):
        watch.check([("pypdf", "6.21.4", True)], query=lambda *_: [])
      self.assertIn("no matching published OSV advisory", path.read_text())
    with self.assertRaises(watch.AdvisoryWatchError):
      watch.check([("pypdf", "6.21.4", True)], query=lambda *_: ["bad\n::notice"])

  def test_workflow_keeps_live_network_off_pr_jobs_and_docs_linked(self):
    workflow = (ROOT / ".github/workflows/pdf-parser-advisories.yml").read_text()
    self.assertIn("schedule:", workflow)
    self.assertIn("workflow_dispatch:", workflow)
    self.assertIn("merge_group:", workflow)
    self.assertIn("tests/general/pdf-parser-advisories.py -v", workflow)
    self.assertIn("github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'", workflow)
    self.assertIn("scripts/pdf_parser_advisory_watch.py", workflow)
    self.assertIn("contents: read", workflow)
    self.assertNotIn("issues: write", workflow)
    docs = (ROOT / "docs/pdf/parser-security-advisories.md").read_text()
    self.assertIn("https://osv.dev/", docs)
    self.assertIn("https://github.com/py-pdf/pypdf/security/advisories", docs)
    self.assertIn("parser-security-advisories.md", (ROOT / "docs/README.md").read_text())


if __name__ == "__main__":
  unittest.main()
