#!/usr/bin/env python3
"""Read-only watch for stable upstream ClamAV engine releases (opener-1161)."""

import json
import os
import re
import sys
import urllib.error
import urllib.request

RELEASES_URL = "https://api.github.com/repos/Cisco-Talos/clamav/releases?per_page=100"
REVIEWED_RELEASES = {"1.4": "clamav-1.4.6", "1.5": "clamav-1.5.4"}
TAG = re.compile(r"clamav-([0-9]+)\.([0-9]+)\.([0-9]+)\Z")
# ClamAV's public releases API includes large changelogs and asset lists.
# Bound the read while accommodating the current ~1.6 MiB release inventory.
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class CompatibilityWatchError(Exception):
  """Public, sanitized failure; never include HTTP responses or credentials."""


def assess_releases(releases):
  """Return changes needing review; never assert an upstream engine is safe."""
  if not isinstance(releases, list) or not releases or len(releases) > 100:
    raise CompatibilityWatchError("Upstream release inventory is invalid or incomplete.")
  newest = {}
  future = set()
  for release in releases:
    if not isinstance(release, dict):
      raise CompatibilityWatchError("Upstream release entry is invalid.")
    if type(release.get("draft")) is not bool or type(release.get("prerelease")) is not bool:
      raise CompatibilityWatchError("Upstream release status could not be verified.")
    if release["draft"] or release["prerelease"]:
      continue
    tag = release.get("tag_name")
    if not isinstance(tag, str):
      raise CompatibilityWatchError("Upstream release tag is missing.")
    match = TAG.fullmatch(tag)
    if not match:
      continue  # Non-stable tags are not treated as supported engine releases.
    expected_url = "https://github.com/Cisco-Talos/clamav/releases/tag/" + tag
    if release.get("html_url") != expected_url:
      raise CompatibilityWatchError("Upstream release origin could not be verified.")
    major, minor, patch = map(int, match.groups())
    branch = f"{major}.{minor}"
    if (major, minor) > (1, 5):
      future.add(tag)
    if branch in REVIEWED_RELEASES and (
        branch not in newest or patch > newest[branch][0]):
      newest[branch] = (patch, tag)

  if set(newest) != set(REVIEWED_RELEASES):
    raise CompatibilityWatchError("Supported ClamAV release branch missing from inventory.")
  changes = []
  for branch, reviewed in sorted(REVIEWED_RELEASES.items()):
    newest_tag = newest[branch][1]
    if newest_tag != reviewed:
      changes.append(f"ClamAV {branch}: reviewed {reviewed}, upstream {newest_tag}")
  changes.extend(f"New ClamAV stable branch: {tag}" for tag in sorted(future))
  return changes


def fetch_releases():
  """Fetch public release metadata only; no binaries, signatures or user PDFs."""
  headers = {"Accept": "application/vnd.github+json",
             "User-Agent": "PDFMagicOpener-ClamAV-Compatibility-Watch"}
  token = os.environ.get("GITHUB_TOKEN")
  if token:
    headers["Authorization"] = "Bearer " + token
  request = urllib.request.Request(RELEASES_URL, headers=headers)
  try:
    with urllib.request.urlopen(request, timeout=12) as response:
      if response.status != 200:
        raise CompatibilityWatchError("Could not verify upstream releases.")
      payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
      raise CompatibilityWatchError("Upstream release inventory is too large.")
    return json.loads(payload)
  except (OSError, ValueError, urllib.error.URLError) as error:
    if isinstance(error, CompatibilityWatchError):
      raise
    raise CompatibilityWatchError("Could not verify upstream ClamAV releases.") from None


def main():
  try:
    changes = assess_releases(fetch_releases())
  except CompatibilityWatchError as error:
    print("ClamAV compatibility watch: " + str(error), file=sys.stderr)
    return 1
  if changes:
    print("ClamAV compatibility review required:", file=sys.stderr)
    for change in changes:
      print("- " + change, file=sys.stderr)
    print("Review https://github.com/Cisco-Talos/clamav/releases and "
          "docs/scanner/compatibility-watch.md before updating the marker.",
          file=sys.stderr)
    return 1
  print("No new stable ClamAV release in tracked branches; this is not a "
        "compatibility or scan-safety certification.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
