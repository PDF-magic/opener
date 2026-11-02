#!/usr/bin/env python3
"""Offline contract tests for official Chromium extension notice monitoring."""

from datetime import date
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
  "chromium_extension_api_watch", ROOT / "scripts/chromium_extension_api_watch.py"
)
watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watch)


def html(*sections):
  return "<html><body><main>" + "".join(
    f"<h2>{title}</h2><p>Posted on {posted}</p><p>Details.</p>"
    for title, posted in sections
  ) + "</main></body></html>"


class FakeResponse:
  def __init__(self, payload, url=watch.SOURCE, mime="text/html"):
    self.payload = payload
    self.url = url
    self.headers = {"Content-Type": mime}

  def __enter__(self):
    return self

  def __exit__(self, *_args):
    return False

  def geturl(self):
    return self.url

  def read(self, size):
    return self.payload[:size]


class TestWatch(unittest.TestCase):
  def test_dated_official_notice_extraction(self):
    document = html(
      ("Chrome 153: New browser.publicSuffix API", "August 25, 2026"),
      ("Chrome 148: The browser namespace", "May 8, 2026"),
      ("Chrome 153: New browser.publicSuffix API", "August 25, 2026")
    )
    self.assertEqual(watch.extract_notices(document), [
      ("Chrome 153: New browser.publicSuffix API", date(2026, 8, 25)),
      ("Chrome 148: The browser namespace", date(2026, 5, 8))
    ])

  def test_undated_headings_and_script_text_not_counted(self):
    document = "<h2>Navigation</h2><script>Posted on December 1, 2026</script>" + html(
      ("API changes", "Sept 09, 2025")
    )
    self.assertEqual(watch.extract_notices(document), [
      ("API changes", date(2025, 9, 9))
    ])

  def test_fails_when_no_dated_articles_or_invalid_date(self):
    for document in ("<html>unavailable</html>", html(("New API", "February 31, 2026"))):
      with self.subTest(document=document), self.assertRaises(watch.WatchError):
        watch.extract_notices(document)

  def test_checkpoint_keeps_existing_notices_nonblocking(self):
    notices = watch.extract_notices(html(("Browser API", "August 25, 2026")))
    report, pending = watch.review(notices)
    self.assertFalse(pending)
    self.assertIn("No notices newer", report)

  def test_new_post_requires_review(self):
    notices = watch.extract_notices(html(
      ("Old API", "October 30, 2026"),
      ("Breaking browser API", "November 2, 2026")
    ))
    report, pending = watch.review(notices)
    self.assertTrue(pending)
    self.assertIn("2026-11-02: Breaking browser API", report)
    self.assertIn(watch.SOURCE, report)

  def test_source_must_be_expected_https_host_path_and_html(self):
    document = html(("Chrome 153 API", "August 25, 2026")).encode()
    for url, mime in (
        ("http://developer.chrome.com/docs/extensions/whats-new", "text/html"),
        ("https://wrong.example/docs/extensions/whats-new", "text/html"),
        ("https://developer.chrome.com/docs/extensions/other", "text/html"),
        (watch.SOURCE, "application/json")):
      with self.subTest(url=url, mime=mime), self.assertRaises(watch.WatchError):
        watch.fetch_notices(lambda *_a, **_kw: FakeResponse(document, url, mime))

  def test_network_content_must_be_bounded_valid_utf8(self):
    with self.assertRaises(watch.WatchError):
      watch.fetch_notices(lambda *_a, **_kw: FakeResponse(b"x" * (watch.MAX_RESPONSE_BYTES + 1)))
    with self.assertRaises(watch.WatchError):
      watch.fetch_notices(lambda *_a, **_kw: FakeResponse(b"\xff"))

  def test_network_error_fails_closed(self):
    def unavailable(*_a, **_kw):
      raise OSError("network down")
    with self.assertRaises(watch.WatchError):
      watch.fetch_notices(unavailable)

  def test_no_notice_list_does_not_claim_success(self):
    with self.assertRaises(watch.WatchError):
      watch.review([])


if __name__ == "__main__":
  unittest.main()
