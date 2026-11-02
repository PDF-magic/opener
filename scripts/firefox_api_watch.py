#!/usr/bin/env python3
"""Watch reviewed Firefox WebExtension API/manifest data, without changing runtime behavior."""

import json
import os
import re
import sys
from urllib import error, parse, request

API_URL = "https://api.github.com/repos/mdn/browser-compat-data/commits"
MAX_RESPONSE_BYTES = 32 * 1024
SHA = re.compile(r"[0-9a-f]{40}\Z")

# Latest commit touching each reviewed MDN BCD file on 2026-11-01.
# A new commit is a human-review signal, NOT proof of a Firefox incompatibility:
# the BCD files contain other browsers' support data too.
REVIEWED = {
  "webextensions/api/action.json": "0efedff8c8b6f131ad029443056bc74e00b1aca2",
  "webextensions/api/downloads.json": "30383d706358d697a0d8693422f0dc44bfb5b06f",
  "webextensions/api/permissions.json": "27bd7e01936db4de9998397502f9491192515f3e",
  "webextensions/manifest/action.json": "00042e87b524003c2b3597fc8887c862f0bb8220",
  "webextensions/manifest/background.json": "d94c8a9469e71e6f9a5ff715a9c0577dadc2892e",
  "webextensions/manifest/browser_specific_settings.json": "c81c53a23c351588f2daeaea38f986d88660a018",
  "webextensions/manifest/host_permissions.json": "5d66484353499b8ad0479701eaa52a28dbd7d931",
  "webextensions/manifest/incognito.json": "0efedff8c8b6f131ad029443056bc74e00b1aca2",
  "webextensions/manifest/manifest_version.json": "59a9a6a49e429bbf922afcf86eb85a8664db0644",
  "webextensions/manifest/optional_permissions.json": "0efedff8c8b6f131ad029443056bc74e00b1aca2",
  "webextensions/manifest/permissions.json": "0efedff8c8b6f131ad029443056bc74e00b1aca2",
}


class FirefoxAPIWatchError(ValueError):
  """The upstream API revision was changed or could not be verified."""


def latest_commit(path, opener=request.urlopen, token=None):
  """Read the newest commit for exactly one approved BCD path."""
  if path not in REVIEWED:
    raise FirefoxAPIWatchError("Unreviewed Firefox API inventory path")
  url = API_URL + "?" + parse.urlencode({"path": path, "per_page": "1"})
  headers = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "PDF-magic-opener-firefox-api-watch",
    "X-GitHub-Api-Version": "2022-11-28",
  }
  if token:
    headers["Authorization"] = "Bearer " + token
  req = request.Request(url, headers=headers, method="GET")
  try:
    with opener(req, timeout=15) as response:
      raw = response.read(MAX_RESPONSE_BYTES + 1)
  except (OSError, error.URLError, TimeoutError) as exc:
    raise FirefoxAPIWatchError("upstream BCD revision query unavailable") from exc
  if len(raw) > MAX_RESPONSE_BYTES:
    raise FirefoxAPIWatchError("upstream BCD response exceeded size bound")
  try:
    data = json.loads(raw)
  except (ValueError, UnicodeError) as exc:
    raise FirefoxAPIWatchError("upstream BCD response is not valid JSON") from exc
  if (not isinstance(data, list) or len(data) != 1
      or not isinstance(data[0], dict)
      or not isinstance(data[0].get("sha"), str)
      or not SHA.fullmatch(data[0]["sha"])):
    raise FirefoxAPIWatchError("upstream BCD revision is missing or malformed")
  return data[0]["sha"]


def check(latest=None):
  """Check every reviewed entry; failure or partial data never means compatible."""
  if not REVIEWED or any(not SHA.fullmatch(pin) for pin in REVIEWED.values()):
    raise FirefoxAPIWatchError("invalid reviewed Firefox API revision inventory")
  if latest is None:
    token = os.environ.get("GITHUB_TOKEN")
    latest = lambda path: latest_commit(path, token=token)
  findings = []
  for path, reviewed_sha in REVIEWED.items():
    try:
      upstream_sha = latest(path)
      if not isinstance(upstream_sha, str) or not SHA.fullmatch(upstream_sha):
        raise FirefoxAPIWatchError("invalid upstream revision")
    except FirefoxAPIWatchError as exc:
      findings.append(f"{path}: {exc}")
      continue
    if upstream_sha != reviewed_sha:
      findings.append(
        f"{path}: reviewed {reviewed_sha}, upstream {upstream_sha}"
      )
  if findings:
    raise FirefoxAPIWatchError(
      "Firefox API review required; see docs/firefox-api-watch.md:\n" +
      "\n".join(findings)
    )
  return len(REVIEWED)


def main():
  try:
    checked = check()
  except FirefoxAPIWatchError as exc:
    print("Firefox WebExtension API watch FAILED:\n" + str(exc), file=sys.stderr)
    return 1
  print(f"Firefox WebExtension API watch: {checked} reviewed upstream paths unchanged.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
