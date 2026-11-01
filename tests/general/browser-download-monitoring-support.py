#!/usr/bin/env python3
"""Keep browser download-monitoring documentation tied to inactive code and the supported catalog."""
from pathlib import Path
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/browser-download-monitoring-support.md"
INDEX = ROOT / "docs/README.md"
CI = ROOT / ".github/workflows/ci.yml"
REGISTRY = ROOT / "browser_registry.py"
EXPECTED = {
    "Brave": ("com.brave.Browser", "Conditional"),
    "Google Chrome": ("com.google.Chrome", "Documented"),
    "Chromium": ("org.chromium.Chromium", "Conditional"),
    "Microsoft Edge": ("com.microsoft.edgemac", "Conditional"),
    "Vivaldi": ("com.vivaldi.Vivaldi", "Conditional"),
    "Opera": ("com.operasoftware.Opera", "Conditional"),
    "Arc": ("company.thebrowser.Browser", "Conditional"),
    "Mozilla Firefox": ("org.mozilla.firefox", "Documented"),
    "Apple Safari": ("com.apple.Safari", "Unverified"),
}


class BrowserDownloadMonitoringSupportTests(unittest.TestCase):
  def test_every_recognized_browser_has_a_conservative_inactive_row(self):
    page = DOC.read_text(encoding="utf-8")
    self.assertIn(
        "| Browser | macOS bundle ID | Download events API | Current PDF Magic Opener monitoring |",
        page,
    )
    rows = []
    for line in page.splitlines():
      fields = [value.strip() for value in line.strip("|").split("|")]
      if (line.startswith("| ") and len(fields) == 4
          and fields[1].startswith("`") and fields[1].endswith("`")
          and fields[3] == "**Inactive**"):
        match = re.match(r"^\\*\\*(Documented|Conditional|Unverified)\\*\\*", fields[2])
        self.assertIsNotNone(match, line)
        rows.append((fields[0], fields[1].strip("`"), match.group(1)))
    self.assertEqual(len(rows), len(EXPECTED))
    self.assertEqual(len(set(name for name, _, _ in rows)), len(EXPECTED))
    actual = {name: (bundle, support) for name, bundle, support in rows}
    self.assertEqual(actual, EXPECTED)

    registry = REGISTRY.read_text(encoding="utf-8")
    for bundle, _ in EXPECTED.values():
      self.assertIn(f'"{bundle}"', registry)
    browser_keys = re.findall(
        r'^    "([a-z]+)": "([^"]+)",$', registry, flags=re.MULTILINE,
    )
    self.assertEqual({bundle for _, bundle in browser_keys},
                     {bundle for bundle, _ in EXPECTED.values()})

  def test_support_labels_do_not_misrepresent_live_monitoring(self):
    page = DOC.read_text(encoding="utf-8")
    for phrase in (
        "inactive in every", "not that a", "**not** a grant",
        "trusted user gesture", "transport-only", "saves a preference",
        "do **not** include PDFs displayed inline",
        "block browser automatic opening", "not** this extension's monitoring",
        "refusal/revocation", "fail closed", "quarantine",
        "selected PDF application",
    ):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase, page)
    self.assertNotIn("**Active** |", page)
    self.assertTrue(
        (ROOT / "extensions/webextension/src/background.js").read_text(
            encoding="utf-8"
        ).strip().endswith("void 0;")
    )
    for manifest_path in (
        "extensions/webextension/manifest.json", "extensions/safari/manifest.json",
    ):
      manifest = json.loads((ROOT / manifest_path).read_text(encoding="utf-8"))
      self.assertEqual(manifest["optional_permissions"], ["downloads"])
      self.assertNotIn("downloads", manifest["permissions"])
      self.assertEqual(manifest["host_permissions"], [])

  def test_documentation_is_linked_and_checked_in_ci(self):
    self.assertIn(
        "(browser-download-monitoring-support.md)",
        INDEX.read_text(encoding="utf-8"),
    )
    workflow = CI.read_text(encoding="utf-8")
    self.assertEqual(
        workflow.count("tests/general/browser-download-monitoring-support.py -v"), 1,
    )
    for target in re.findall(r"\]\(([^)]+\.md)\)", DOC.read_text()):
      if target.startswith(("http:", "https:")):
        continue
      with self.subTest(target=target):
        self.assertTrue((DOC.parent / target).resolve().is_file(), target)


if __name__ == "__main__":
  unittest.main()
