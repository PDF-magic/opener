#!/usr/bin/env python3
"""Watch published OSV advisories for reviewed PDF parser versions only.

No PDF content, scanner, user configuration, or authentication is accessed.
"""

import json
import os
from pathlib import Path
import re
import sys
from urllib import error, request

import dependency_vulnerability_audit as dependencies
import check_dependency_licenses as licenses

ROOT = Path(__file__).resolve().parents[1]
OSV_URL = "https://api.osv.dev/v1/query"
PARSER_PACKAGES = frozenset({"pypdf", "pymupdf"})
ADVISORY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z")
MAX_PAGES = 20
MAX_RESPONSE_BYTES = 1_000_000


class AdvisoryWatchError(ValueError):
  """An advisory feed or parser inventory could not be trusted."""


def inventory(root=ROOT):
  """Use the existing license/vulnerability review rather than a second pin list."""
  current, legacy = dependencies.pins(root)
  expected = {
    (name, version)
    for name in PARSER_PACKAGES
    for version in licenses.REVIEWED[name][0]
  }
  watched = {(name, version) for name, version in current | legacy
             if name in PARSER_PACKAGES}
  if watched != expected or not (current & watched):
    raise AdvisoryWatchError("PDF parser advisory inventory is incomplete")
  return [(name, version, (name, version) in current)
          for name, version in sorted(watched)]


def query_osv(name, version, page_token=None, opener=request.urlopen):
  body = {"package": {"ecosystem": "PyPI", "name": name}, "version": version}
  if page_token is not None:
    body["page_token"] = page_token
  payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
  req = request.Request(OSV_URL, data=payload, headers={
    "Content-Type": "application/json", "Accept": "application/json",
    "User-Agent": "PDF-magic-parser-advisory-watch/1"
  }, method="POST")
  try:
    with opener(req, timeout=15) as response:
      raw = response.read(MAX_RESPONSE_BYTES + 1)
  except (OSError, error.URLError, TimeoutError) as exc:
    raise AdvisoryWatchError("OSV advisory service unavailable") from exc
  if len(raw) > MAX_RESPONSE_BYTES:
    raise AdvisoryWatchError("OSV advisory response too large")
  try:
    data = json.loads(raw)
  except (ValueError, UnicodeError) as exc:
    raise AdvisoryWatchError("OSV advisory response is not JSON") from exc
  if not isinstance(data, dict):
    raise AdvisoryWatchError("OSV advisory response is not an object")
  vulns = data.get("vulns", [])
  if not isinstance(vulns, list):
    raise AdvisoryWatchError("OSV advisory list is malformed")
  ids = []
  for vuln in vulns:
    if (not isinstance(vuln, dict) or not isinstance(vuln.get("id"), str)
        or not ADVISORY_ID.fullmatch(vuln["id"])):
      raise AdvisoryWatchError("OSV advisory identifier is malformed")
    ids.append(vuln["id"])
  token = data.get("next_page_token")
  if token is not None and (not isinstance(token, str) or not token or len(token) > 512):
    raise AdvisoryWatchError("OSV pagination token is malformed")
  return ids, token


def advisories(name, version, query=query_osv):
  seen = set()
  token = None
  ids = set()
  for _ in range(MAX_PAGES):
    found, next_token = query(name, version, token)
    if not isinstance(found, list) or any(
        not isinstance(item, str) or not ADVISORY_ID.fullmatch(item) for item in found):
      raise AdvisoryWatchError("Incomplete parser advisory query")
    ids.update(found)
    if next_token is None:
      return sorted(ids)
    if not isinstance(next_token, str) or not next_token or next_token in seen:
      raise AdvisoryWatchError("Repeated or invalid OSV page token")
    seen.add(next_token)
    token = next_token
  raise AdvisoryWatchError("OSV advisory pagination exceeded safety limit")


def check(watched, query=advisories):
  rows = []
  blocked = False
  for name, version, current in watched:
    ids = query(name, version)
    if not isinstance(ids, list) or any(
        not isinstance(item, str) or not ADVISORY_ID.fullmatch(item) for item in ids):
      raise AdvisoryWatchError("Invalid advisory scan results")
    label = "current optional parser" if current else "legacy CI-only parser"
    rows.append(f"- `{name}=={version}` ({label}): " + (
      ", ".join(f"[ {item} ](https://osv.dev/vulnerability/{item})" for item in sorted(set(ids)))
      if ids else "no matching published OSV advisory"))
    if ids and current:
      blocked = True
    if ids:
      print(f"::warning title=PDF parser advisory::{name}=={version}: {', '.join(sorted(set(ids)))}")
    else:
      print(f"{name}=={version}: no matching published OSV advisory")
  report = "## PDF parser security advisories\n\n" + "\n".join(rows) + "\n"
  if os.environ.get("GITHUB_STEP_SUMMARY"):
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
      summary.write(report)
  else:
    print(report)
  if blocked:
    raise AdvisoryWatchError("Published advisory affects the current optional PDF parser pin")


def main():
  try:
    check(inventory())
  except (AdvisoryWatchError, OSError, ValueError) as exc:
    print("PDF parser advisory watch FAILED: " + str(exc), file=sys.stderr)
    return 1
  return 0


if __name__ == "__main__":
  sys.exit(main())
