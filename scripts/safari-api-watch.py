#!/usr/bin/env python3
"""Read-only watch for changes in WebKit's official Safari extension API notes.

PR tests are hermetic; only scheduled/manual runs fetch the public WebKit feed.
"""

from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
import os
import re
import sys
from urllib import error, request
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

FEED_URL = "https://webkit.org/feed/"
WATCH_START = date.fromisoformat("2026-11-01")
MAX_BYTES = 4_000_000
MAX_ITEMS = 100
POST_PATH = re.compile(r"/blog/[0-9]+/[a-zA-Z0-9_.-]+/?\Z")
API_TERMS = re.compile(
  r"\b(?:web[ -]?extensions?|safari (?:app )?extensions?|native messaging)\b",
  re.IGNORECASE,
)
SAFARI_RELEASE = re.compile(r"\b(?:WebKit Features for Safari|Safari Technology Preview)\b", re.I)
MARKUP = re.compile(r"<[^>]*>")


class SafariAPIWatchError(ValueError):
  """The watch cannot establish coverage or has pending API review."""


def fetch_feed(opener=request.urlopen):
  req = request.Request(FEED_URL, headers={
    "Accept": "application/rss+xml, application/xml;q=0.9",
    "User-Agent": "PDF-magic-safari-api-watch/1",
  })
  try:
    with opener(req, timeout=20) as response:
      if response.geturl() != FEED_URL:
        raise SafariAPIWatchError("Unexpected upstream feed redirect")
      data = response.read(MAX_BYTES + 1)
  except (OSError, error.URLError, TimeoutError) as exc:
    raise SafariAPIWatchError("Official WebKit feed unavailable") from exc
  if len(data) > MAX_BYTES:
    raise SafariAPIWatchError("Official WebKit feed exceeds size limit")
  return data


def parse_feed(data, *, now=None):
  """Validate the RSS window before treating absence of new entries as clean."""
  if now is None:
    now = datetime.now(timezone.utc)
  if now.tzinfo is None:
    raise SafariAPIWatchError("Review time must be timezone-aware")
  try:
    root = ET.fromstring(data)
  except (ET.ParseError, TypeError, ValueError) as exc:
    raise SafariAPIWatchError("Official WebKit RSS is malformed") from exc
  if root.tag != "rss" or root.find("channel") is None:
    raise SafariAPIWatchError("Expected an RSS channel")
  items = root.findall("./channel/item")
  if not items or len(items) > MAX_ITEMS:
    raise SafariAPIWatchError("Missing or unbounded RSS entries")

  posts = []
  seen = set()
  previous_date = None
  for item in items:
    title = item.findtext("title")
    link = item.findtext("link")
    pub_date = item.findtext("pubDate")
    if not title or not link or not pub_date:
      raise SafariAPIWatchError("Incomplete WebKit RSS item")
    parsed = urlsplit(link)
    if (parsed.scheme != "https" or parsed.netloc != "webkit.org" or
        not POST_PATH.fullmatch(parsed.path) or parsed.query or parsed.fragment):
      raise SafariAPIWatchError("Unexpected WebKit article link")
    canonical = f"https://webkit.org{parsed.path}"
    if canonical in seen:
      raise SafariAPIWatchError("Duplicate WebKit RSS item")
    seen.add(canonical)
    try:
      published = parsedate_to_datetime(pub_date)
    except (TypeError, ValueError, IndexError) as exc:
      raise SafariAPIWatchError("Invalid WebKit article date") from exc
    if published.tzinfo is None:
      raise SafariAPIWatchError("WebKit article date lacks timezone")
    published = published.astimezone(timezone.utc)
    if published > now + timedelta(days=2):
      raise SafariAPIWatchError("WebKit RSS contains future-dated articles")
    if previous_date is not None and published > previous_date:
      raise SafariAPIWatchError("WebKit RSS is not newest-first")
    previous_date = published
    description = " ".join(item.itertext())
    plain = unescape(MARKUP.sub(" ", description))
    relevant = bool(API_TERMS.search(plain) or SAFARI_RELEASE.search(title))
    posts.append((published.date(), canonical, relevant))

  if posts[-1][0] > WATCH_START:
    raise SafariAPIWatchError(
      "WebKit RSS no longer reaches the review baseline; review upstream "
      "and advance WATCH_START without skipping unreviewed articles")
  return [(published, url) for published, url, relevant in posts
          if published > WATCH_START and relevant]


def check(data, *, now=None):
  pending = parse_feed(data, now=now)
  lines = [
    "## Safari extension API watch",
    "",
    f"Source: {FEED_URL}",
    f"Review baseline (UTC): {WATCH_START.isoformat()}",
    "",
  ]
  if pending:
    lines.append("New upstream Safari/WebExtensions material requires human review:")
    lines.extend(f"- {published}: {url}" for published, url in pending)
    lines.append("")
    lines.append("Review API/manifest/permission/native messaging changes and Safari "
                 "tests before advancing the baseline; do not auto-enable new APIs.")
  else:
    lines.append("No matching articles since the baseline within the verified feed window. "
                 "This is not a Safari compatibility certification.")
  report = "\n".join(lines) + "\n"
  if os.environ.get("GITHUB_STEP_SUMMARY"):
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
      handle.write(report)
  print(report)
  if pending:
    raise SafariAPIWatchError("Unreviewed official Safari extension API updates")


def main():
  try:
    check(fetch_feed())
  except (SafariAPIWatchError, OSError, ValueError) as exc:
    print("Safari extension API watch FAILED: " + str(exc), file=sys.stderr)
    return 1
  return 0


if __name__ == "__main__":
  sys.exit(main())
