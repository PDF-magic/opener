#!/usr/bin/env python3
"""Read-only watch for newly posted official Chrome Extensions platform notices."""

from datetime import date, datetime
from html.parser import HTMLParser
import os
import re
import sys
from urllib import error, request
from urllib.parse import urlparse

SOURCE = "https://developer.chrome.com/docs/extensions/whats-new"
# Advance only after reviewing every newer notice in a separate source PR.
REVIEWED_THROUGH = date(2026, 11, 1)
MAX_RESPONSE_BYTES = 2_000_000
POSTED = re.compile(
  r"\bPosted on\s+"
  r"(January|February|March|April|May|June|July|August|September|Sept|October|November|December)"
  r"\s+(\d{1,2}),?\s+(20\d{2})\b", re.IGNORECASE
)


class WatchError(ValueError):
  """The upstream notices could not be verified or need a maintainer review."""


class NewsParser(HTMLParser):
  """Extract notice titles and dates from visible headings and adjacent text."""

  def __init__(self):
    super().__init__(convert_charrefs=True)
    self.ignore = 0
    self.heading = None
    self.depth = 0
    self.title = []
    self.body = []
    self.sections = []

  def handle_starttag(self, tag, attrs):
    if tag in ("script", "style", "svg", "template"):
      self.ignore += 1
    if self.ignore:
      return
    if tag in ("h2", "h3", "h4"):
      self.finish()
      self.heading = tag
      self.depth = 1
    elif self.heading is not None and self.depth:
      self.depth += 1

  def handle_endtag(self, tag):
    if tag in ("script", "style", "svg", "template") and self.ignore:
      self.ignore -= 1
      return
    if self.ignore:
      return
    if self.heading and tag == self.heading:
      self.depth = 0
    elif self.depth:
      self.depth -= 1

  def handle_data(self, data):
    if self.ignore:
      return
    if self.heading is not None:
      (self.title if self.depth else self.body).append(data)

  def finish(self):
    if self.heading:
      self.sections.append((" ".join(" ".join(self.title).split()),
                            " ".join(" ".join(self.body).split())))
    self.heading = None
    self.title = []
    self.body = []
    self.depth = 0


def extract_notices(document):
  if not isinstance(document, str):
    raise WatchError("Extension notices must be HTML text")
  parser = NewsParser()
  parser.feed(document)
  parser.finish()
  notices = []
  seen = set()
  for title, body in parser.sections:
    match = POSTED.search(body)
    if not match:
      continue
    if not title or len(title) > 200:
      raise WatchError("Malformed upstream notice heading")
    month = "September" if match.group(1).lower() == "sept" else match.group(1)
    try:
      published = datetime.strptime(
        f"{month} {match.group(2)} {match.group(3)}", "%B %d %Y"
      ).date()
    except ValueError as exc:
      raise WatchError("Malformed upstream notice date") from exc
    key = (title, published)
    if key not in seen:
      notices.append(key)
      seen.add(key)
  if not notices:
    raise WatchError("No dated Chrome Extensions notices found (page format changed?)")
  return notices


def fetch_notices(opener=request.urlopen):
  req = request.Request(SOURCE, headers={
    "Accept": "text/html", "User-Agent": "PDFMagicOpener-Chromium-API-Watch/1"
  })
  try:
    with opener(req, timeout=20) as response:
      final = urlparse(response.geturl())
      if (final.scheme, final.hostname, final.path) != (
          "https", "developer.chrome.com", "/docs/extensions/whats-new"):
        raise WatchError("Unexpected upstream redirect")
      if "text/html" not in response.headers.get("Content-Type", ""):
        raise WatchError("Chrome Extensions notices were not HTML")
      payload = response.read(MAX_RESPONSE_BYTES + 1)
  except (OSError, error.URLError, TimeoutError) as exc:
    raise WatchError("Chrome Extensions notices could not be downloaded") from exc
  if len(payload) > MAX_RESPONSE_BYTES:
    raise WatchError("Chrome Extensions notice response exceeded byte limit")
  try:
    return extract_notices(payload.decode("utf-8", errors="strict"))
  except UnicodeError as exc:
    raise WatchError("Chrome Extensions notice response is not UTF-8") from exc


def review(notices, cutoff=REVIEWED_THROUGH):
  if not notices:
    raise WatchError("No upstream notices available for review")
  if not isinstance(cutoff, date):
    raise WatchError("Invalid reviewed-through cutoff")
  new = sorted((title, posted) for title, posted in notices if posted > cutoff)
  lines = [
    "## Chromium Extensions API watch",
    "",
    f"Source: {SOURCE}",
    f"Maintainer reviewed-through date: {cutoff.isoformat()}",
    f"Dated upstream notices parsed: {len(notices)}",
    ""
  ]
  if new:
    lines.append("Review newly posted upstream notices before advancing the checkpoint:")
    lines.extend(f"- {posted.isoformat()}: {title}" for title, posted in new)
  else:
    lines.append("No notices newer than the reviewed-through date.")
  return "\n".join(lines) + "\n", bool(new)


def main():
  try:
    report, pending = review(fetch_notices())
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
      with open(summary, "a", encoding="utf-8") as output:
        output.write(report)
    print(report)
    if pending:
      raise WatchError("New Chromium extension notices require a compatibility review")
  except (WatchError, OSError) as exc:
    print("Chromium extension API watch FAILED: " + str(exc), file=sys.stderr)
    return 1
  return 0


if __name__ == "__main__":
  sys.exit(main())
