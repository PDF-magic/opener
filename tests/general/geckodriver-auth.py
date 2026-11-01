#!/usr/bin/env python3
"""Keep Firefox CI geckodriver downloads off GitHub's anonymous API limit."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"
ACTION = re.compile(r"^(?P<indent> *)- uses: browser-actions/setup-geckodriver@\S+\s*$")
EXPECTED_TOKEN = "token: ${{ github.token }}"


def missing_authentication(source):
  """Return the action line numbers missing a matching per-step token input."""
  lines = source.splitlines()
  missing = []
  seen = 0
  for index, line in enumerate(lines):
    match = ACTION.match(line)
    if match is None:
      continue
    seen += 1
    depth = len(match.group("indent"))
    following = []
    for candidate in lines[index + 1:]:
      whitespace = len(candidate) - len(candidate.lstrip(" "))
      if candidate.lstrip().startswith("- ") and whitespace <= depth:
        break
      following.append(candidate)
    # Do not accept a token from a different action, later step, or job.
    if (
      " " * (depth + 2) + "with:" not in following
      or " " * (depth + 4) + EXPECTED_TOKEN not in following
    ):
      missing.append(index + 1)
  return seen, missing


class GeckodriverAuthTests(unittest.TestCase):
  def test_all_geckodriver_workflows_pass_readonly_github_token(self):
    usages = 0
    known = {
      "ci.yml",
      "browser-native-pdf-downloads.yml",
      "firefox-download-macos-open.yml",
    }
    visited = set()
    for path in WORKFLOWS.glob("*.yml"):
      source = path.read_text(encoding="utf-8")
      count, missing = missing_authentication(source)
      usages += count
      if count:
        visited.add(path.name)
      self.assertEqual(missing, [], path.name)
    self.assertEqual(visited, known)
    self.assertEqual(usages, 3)

  def test_token_from_another_step_does_not_pass(self):
    test_source = (
      "      - uses: browser-actions/setup-geckodriver@latest\n"
      "      - name: Other step\n"
      "        with:\n"
      "          token: " + EXPECTED_TOKEN.split(": ", 1)[1] + "\n"
    )
    self.assertEqual(missing_authentication(test_source), (1, [1]))
    self.assertEqual(missing_authentication(
      "      - uses: browser-actions/setup-geckodriver@latest\n"
      "        with:\n"
      "          token: " + EXPECTED_TOKEN.split(": ", 1)[1] + "\n"
    ), (1, []))

  def test_regression_runs_in_scanner_ci(self):
    workflow = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    self.assertIn("PYTHONPATH=. python3 tests/general/geckodriver-auth.py -v",
                  workflow)
    # Token scope stays read-only; the suite does not require a PAT or new secrets.
    self.assertIn("permissions:\n  contents: read", workflow)


if __name__ == "__main__":
  unittest.main()
