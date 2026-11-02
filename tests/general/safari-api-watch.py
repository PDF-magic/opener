#!/usr/bin/env python3
"""Offline regressions for upstream Safari extension API-change monitoring."""

from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import safari_api_watch as watch

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)


def entry(title, date, num, *, description=""):
  return (f"<item><title>{escape(title)}</title>"
          f"<link>https://webkit.org/blog/{num}/post-{num}/</link>"
          f"<pubDate>{date}</pubDate>"
          f"<description>{escape(description)}</description></item>")


def feed(*items):
  return ("<rss version='2.0'><channel><title>WebKit</title>"
          + "".join(items) + "</channel></rss>").encode("utf-8")


BASE = entry("Baseline post", "Sat, 31 Oct 2026 12:00:00 +0000", 1)
NEW = entry("WebKit Features for Safari 27.1", "Tue, 03 Nov 2026 12:00:00 +0000", 2)
OTHER = entry("CSS styling improvements", "Mon, 02 Nov 2026 12:00:00 +0000", 3)


class Response:
  def __init__(self, content, url=watch.FEED_URL):
    self.content = content
    self.url = url

  def __enter__(self):
    return self

  def __exit__(self, *_):
    return False

  def read(self, size):
    return self.content[:size]

  def geturl(self):
    return self.url


class SafariAPIWatchTests(unittest.TestCase):
  def test_official_source_and_bounded_fetch(self):
    def opener(req, timeout):
      self.assertEqual(req.full_url, watch.FEED_URL)
      self.assertEqual(timeout, 20)
      return Response(b"<rss/>")
    self.assertEqual(watch.fetch_feed(opener), b"<rss/>")
    for response in (Response(b"ok", "https://example.com/feed/"),
                     Response(b"x" * (watch.MAX_BYTES + 1))):
      with self.subTest(url=response.url), self.assertRaises(watch.SafariAPIWatchError):
        watch.fetch_feed(opener=lambda *_args, **_kwargs: response)
    with self.assertRaises(watch.SafariAPIWatchError):
      watch.fetch_feed(opener=mock.Mock(side_effect=OSError("offline")))

  def test_relevant_release_and_content_changes_trigger_review(self):
    in_body = entry("Platform changes", "Mon, 02 Nov 2026 12:00:00 +0000", 4,
                    description="New native messaging permission behavior")
    posts = watch.parse_feed(feed(NEW, in_body, BASE), now=NOW)
    self.assertEqual([url for _, url in posts], [
      "https://webkit.org/blog/2/post-2/", "https://webkit.org/blog/4/post-4/"])
    with self.assertRaisesRegex(watch.SafariAPIWatchError, "Unreviewed"):
      watch.check(feed(NEW, BASE), now=NOW)

  def test_unrelated_articles_pass_but_do_not_advance_baseline(self):
    with redirect_stdout(io.StringIO()) as output:
      watch.check(feed(OTHER, BASE), now=NOW)
    self.assertIn("not a Safari compatibility certification", output.getvalue())

  def test_feed_gaps_and_empty_or_invalid_rss_fail_closed(self):
    cases = [b"", b"<rss/>", b"<html/>", feed(),
             feed(NEW), feed(BASE, NEW),
             feed(entry("Unknown", "not a date", 5), BASE),
             feed(entry("Future", "Fri, 20 Nov 2026 12:00:00 +0000", 5), BASE),
             feed(BASE, BASE)]
    for data in cases:
      with self.subTest(body=data[:70]), self.assertRaises(watch.SafariAPIWatchError):
        watch.parse_feed(data, now=NOW)

  def test_rejects_external_or_suspicious_article_urls(self):
    for link in ("http://webkit.org/blog/2/post-2/",
                 "https://evil.example/blog/2/post-2/",
                 "https://webkit.org/blog/2/post-2/?tracking=1",
                 "https://webkit.org/blog/2/post-2/#fragment",
                 "https://webkit.org/blog/2/../unsafe/"):
      case = NEW.replace("https://webkit.org/blog/2/post-2/", link)
      with self.subTest(link=link), self.assertRaises(watch.SafariAPIWatchError):
        watch.parse_feed(feed(case, BASE), now=NOW)

  def test_summary_only_includes_official_article_links(self):
    with tempfile.TemporaryDirectory() as temp:
      summary = Path(temp) / "summary.md"
      with mock.patch.dict("os.environ", {"GITHUB_STEP_SUMMARY": str(summary)}):
        with redirect_stdout(io.StringIO()), self.assertRaises(watch.SafariAPIWatchError):
          watch.check(feed(NEW, BASE), now=NOW)
      report = summary.read_text()
      self.assertIn("https://webkit.org/blog/2/post-2/", report)
      self.assertIn("Review baseline", report)

  def test_workflow_contract_and_safari_safety_scope(self):
    workflow = (ROOT / ".github/workflows/safari-api-watch.yml").read_text()
    self.assertIn("merge_group:", workflow)
    self.assertIn("pull_request:", workflow)
    self.assertIn("schedule:", workflow)
    self.assertIn("workflow_dispatch:", workflow)
    self.assertIn("tests/general/safari-api-watch.py -v", workflow)
    self.assertIn("scripts/safari_api_watch.py", workflow)
    self.assertIn("github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'", workflow)
    self.assertIn("contents: read", workflow)
    self.assertNotIn("secrets.", workflow)
    self.assertNotIn("issues: write", workflow)
    docs = (ROOT / "docs/safari-extension-api-watch.md").read_text()
    self.assertIn("https://webkit.org/feed/", docs)
    self.assertIn("https://developer.apple.com/documentation/safariservices/safari-web-extensions", docs)
    self.assertIn("safari-extension-api-watch.md", (ROOT / "docs/README.md").read_text())


if __name__ == "__main__":
  unittest.main()
