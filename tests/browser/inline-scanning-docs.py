#!/usr/bin/env python3
"""Keep inline PDF scanning documentation aligned with the disabled runtime."""

import json
from pathlib import Path
import re
import unittest

from browser_registry import SUPPORTED_BROWSERS

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/inline-pdf-scanning-support.md"
README = ROOT / "README.md"
CAPABILITIES = ROOT / "docs/browser-automatic-interception-capabilities.json"
RUNTIME = ROOT / "extensions/webextension/src/automatic-interception-capability-matrix.js"


class InlineScanningDocumentationTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.guide = GUIDE.read_text(encoding="utf-8")
    cls.readme = README.read_text(encoding="utf-8")
    cls.matrix = json.loads(CAPABILITIES.read_text(encoding="utf-8"))
    cls.runtime = RUNTIME.read_text(encoding="utf-8")

  def test_every_registered_browser_is_documented_as_inactive(self):
    section = self.guide.split("## Browser-by-browser support\n", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(
      r"^\| ([^|]+) \| `([^`]+)` \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$",
      section, re.MULTILINE
    )
    self.assertEqual(len(rows), len(SUPPORTED_BROWSERS))
    matrix_by_bundle = {item["bundleId"]: item for item in self.matrix["browsers"]}
    self.assertEqual(set(matrix_by_bundle), set(SUPPORTED_BROWSERS.values()))
    self.assertEqual({bundle for _, bundle, _, _, _ in rows}, set(matrix_by_bundle))
    for name, bundle, viewing, scan, limitation in rows:
      with self.subTest(browser=bundle):
        self.assertEqual(name, matrix_by_bundle[bundle]["name"])
        self.assertEqual(scan.strip(), "**No — inactive**")
        self.assertTrue(viewing.strip())
        self.assertTrue(limitation.strip())
        self.assertFalse(matrix_by_bundle[bundle]["allPathPreOpenVetoProven"])

  def test_guide_matches_inactive_implementation(self):
    self.assertFalse(self.matrix["interceptionEnabled"])
    self.assertFalse(self.matrix["allPathPreOpenVetoProven"])
    self.assertIn('deployment: "inactive"', self.runtime)
    self.assertIn('nativeScanInterlockVerified: false', self.runtime)
    for token in ("Firefox", "webRequest.filterResponseData", "policy-installed-only",
                  "Safari", "PDF.js", "ClamAV", "quarantine", "Finder",
                  "blob:", "data:", "file:", "not** the same thing"):
      with self.subTest(token=token):
        self.assertIn(token, self.guide)

  def test_readme_and_evidence_links(self):
    section = self.readme.split("## Browser-independent PDF opening\n", 1)[1].split("\n## ", 1)[0]
    self.assertIn(
      "[inline PDF scanning support](docs/inline-pdf-scanning-support.md)",
      section
    )
    for path in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", self.guide):
      if "://" not in path:
        with self.subTest(path=path):
          self.assertTrue((GUIDE.parent / path).exists(), path)


if __name__ == "__main__":
  unittest.main()
