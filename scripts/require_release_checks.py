#!/usr/bin/env python3
"""Fail-closed guard for the manual, source-only GitHub release path."""

import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPOSITORY = "PDF-magic/opener"
REQUIRED_CHECKS = (
  "scanner-tests",
  "Standard baseline EICAR with real ClamAV",
  "macos-build",
  "macOS-native integration",
  "PDF parser filesystem confinement (macOS)",
  "Chrome package smoke test",
  "Python lint and WebExtension syntax",
  "Audit pinned Python dependencies",
  "Verify unsigned packages and signing prerequisites",
  "Release gating regression suite",
)
TAG_PATTERN = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?\Z")
SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
ROOT = Path(__file__).resolve().parents[1]


class GateError(Exception):
  """Safe-to-print release refusal."""


def ensure_context(repository, ref, sha, tag, distribution_doc):
  if repository != REPOSITORY or ref != "refs/heads/main":
    raise GateError("Release must run against PDF-magic/opener main")
  if not SHA_PATTERN.fullmatch(sha):
    raise GateError("Release source SHA is missing or invalid")
  if not TAG_PATTERN.fullmatch(tag):
    raise GateError("Release tag must be a semantic version beginning with v")
  if "**Status: RELEASE READY.**" not in distribution_doc or "NOT RELEASE READY" in distribution_doc:
    raise GateError("Distribution remains NOT RELEASE READY; resolve and review signing and publication blockers first")


def ensure_checks(check_runs):
  failures = []
  for required in REQUIRED_CHECKS:
    matches = [run for run in check_runs if run.get("name") == required
               and (run.get("app") or {}).get("slug") == "github-actions"]
    if len(matches) != 1:
      failures.append(f"{required}: expected exactly one trusted GitHub Actions check, found {len(matches)}")
    elif matches[0].get("status") != "completed" or matches[0].get("conclusion") != "success":
      failures.append(f"{required}: not successful (including pending, skipped or cancelled)")
  if failures:
    raise GateError("Critical checks block release:\n" + "\n".join(failures))


def github_json(path, token):
  request = Request(
    "https://api.github.com/repos/" + REPOSITORY + "/" + path,
    headers={
      "Authorization": "Bearer " + token,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  )
  try:
    with urlopen(request, timeout=20) as response:
      return json.load(response)
  except (HTTPError, URLError, TimeoutError, ValueError) as error:
    # Do not print response bodies, tokens, or URLs containing credentials.
    raise GateError("GitHub verification API was unavailable or invalid") from error


def resolve_tag(tag, token):
  reference = github_json("git/ref/tags/" + tag, token)
  target = reference.get("object") or {}
  for _ in range(4):
    if target.get("type") == "commit" and SHA_PATTERN.fullmatch(target.get("sha", "")):
      return target["sha"]
    if target.get("type") != "tag" or not SHA_PATTERN.fullmatch(target.get("sha", "")):
      break
    target = (github_json("git/tags/" + target["sha"], token).get("object") or {})
  raise GateError("Release tag does not resolve to a commit")


def get_check_runs(sha, token):
  all_runs = []
  for page in range(1, 11):
    response = github_json(f"commits/{sha}/check-runs?per_page=100&page={page}", token)
    runs = response.get("check_runs")
    if not isinstance(runs, list):
      raise GateError("Malformed critical-check result")
    all_runs.extend(runs)
    if len(runs) < 100:
      if response.get("total_count") != len(all_runs):
        raise GateError("Incomplete critical-check listing")
      return all_runs
  raise GateError("Critical-check listing exceeds the verification limit")


def verify_release(repository, ref, sha, tag, distribution_doc, token):
  ensure_context(repository, ref, sha, tag, distribution_doc)
  if not token:
    raise GateError("GitHub verification token is missing")
  branch = github_json("branches/main", token)
  if (branch.get("commit") or {}).get("sha") != sha:
    raise GateError("main changed; re-run the release gate on its new tip")
  if resolve_tag(tag, token) != sha:
    raise GateError("Release tag does not point to the exact verified main commit")
  ensure_checks(get_check_runs(sha, token))


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--tag", required=True)
  args = parser.parse_args(argv)
  try:
    doc = (ROOT / "docs/browser-extension-distribution.md").read_text(encoding="utf-8")
    verify_release(
      os.environ.get("GITHUB_REPOSITORY", ""),
      os.environ.get("GITHUB_REF", ""),
      os.environ.get("GITHUB_SHA", ""),
      args.tag, doc, os.environ.get("GH_TOKEN", ""),
    )
  except (OSError, GateError) as error:
    print("Release blocked: " + (str(error) if isinstance(error, GateError)
                                 else "distribution readiness document unavailable"), file=sys.stderr)
    return 1
  print("Release gate passed for the exact main SHA and existing tag.")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
