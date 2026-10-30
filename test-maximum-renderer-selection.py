#!/usr/bin/env python3
"""Review and pin the selected Maximum PDF renderer (opener-0483)."""

from importlib.metadata import version
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent
WORKFLOW = (ROOT / ".github/workflows/consolidated-checks.yml").read_text(encoding="utf-8")
DECISION = (ROOT / "docs/maximum/renderer-selection.md").read_text(encoding="utf-8")
WORKER = (ROOT / "maximum_render_worker.py").read_text(encoding="utf-8")
LICENSE = (ROOT / "LICENSE").read_text(encoding="utf-8")


class MaximumRendererSelectionTests(unittest.TestCase):
    def test_reviewed_renderer_version_is_installed_and_exactly_pinned(self):
        self.assertEqual(version("PyMuPDF"), "2.0")
        self.assertIn("pymupdf==2.0", WORKFLOW)
        self.assertIn("--no-deps", WORKFLOW)
        self.assertIn("python3 test-maximum-renderer-selection.py -v", WORKFLOW)

    def test_security_review_records_current_release_and_advisories(self):
        for evidence in (
            "Review date: 2026-10-29.",
            "PyMuPDF 2.0",
            "MuPDF 1.28.5",
            "CVE-2026-82035",
            "GHSA-434w-92hw-f2m3",
            "CVE-2026-3029",
            "GHSA-cxqh-p2w9-fmr7",
            "1.28.2",
            "no provenance attestations",
            "https://pymupdf.io/changelog",
            "https://pypi.org/project/pymupdf/2.0/",
        ):
            with self.subTest(evidence=evidence):
                self.assertIn(evidence, DECISION)

    def test_license_review_matches_repository_and_upstream_license(self):
        self.assertIn("GNU AFFERO GENERAL PUBLIC LICENSE", LICENSE)
        for evidence in (
            "AGPLv3",
            "Artifex commercial license",
            "https://pymupdf.io/licensing",
            "../LICENSE",
        ):
            with self.subTest(evidence=evidence):
                self.assertIn(evidence, DECISION)

    def test_native_renderer_is_imported_only_after_worker_limits(self):
        self.assertLess(WORKER.index("_apply_limits()"), WORKER.index("import pymupdf"))


if __name__ == "__main__":
    unittest.main()
