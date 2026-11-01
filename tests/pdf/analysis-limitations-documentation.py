#!/usr/bin/env python3
"""Keep the structural-analysis limitations documentation tied to implemented facts."""

from pathlib import Path
import unittest

from pdf_structure_parser import (
  MAX_STRUCTURE_DECOMPRESSED_STREAM_BYTES,
  MAX_STRUCTURE_INPUT_BYTES,
  MAX_STRUCTURE_OBJECTS,
  MAX_STRUCTURE_PAGES,
  MAX_STRUCTURE_RECURSION_DEPTH,
  MAX_STRUCTURE_TOTAL_DECOMPRESSED_BYTES,
  PDFStructure,
  PDFStructureFailureCode,
  PDFStructureParseFailure,
)

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = ROOT / "docs/pdf/analysis-limitations.md"
INDEX = ROOT / "docs/README.md"


class StructuralAnalysisLimitationsDocumentationTests(unittest.TestCase):
  def test_index_links_to_limitations_and_related_pages_exist(self):
    text = DOCUMENT.read_text(encoding="utf-8")
    self.assertIn(
      "[PDF structural analysis limitations](pdf/analysis-limitations.md)",
      INDEX.read_text(encoding="utf-8"),
    )
    for destination in (
      "structure-parser.md",
      "unsupported-feature-inspection.md",
      "incremental-revisions.md",
      "parser-evaluation.md",
      "../unsupported-pdf-features.md",
    ):
      with self.subTest(destination=destination):
        self.assertIn(f"({destination})", text)
        self.assertTrue((DOCUMENT.parent / destination).is_file())

  def test_documented_resource_limits_match_the_parser(self):
    text = DOCUMENT.read_text(encoding="utf-8")
    mib = 1024 * 1024
    limits = (
      (MAX_STRUCTURE_INPUT_BYTES // mib, "MiB input"),
      (MAX_STRUCTURE_OBJECTS, "indexed indirect objects"),
      (MAX_STRUCTURE_PAGES, "pages"),
      (MAX_STRUCTURE_RECURSION_DEPTH, "nested structure levels"),
      (MAX_STRUCTURE_DECOMPRESSED_STREAM_BYTES // mib, "MiB per indexed stream"),
      (MAX_STRUCTURE_TOTAL_DECOMPRESSED_BYTES // mib, "MiB\ncumulative"),
    )
    for value, label in limits:
      with self.subTest(label=label):
        self.assertIn(f"{value:,} {label}", text)

  def test_success_is_narrow_evidence_and_not_an_open_verdict(self):
    text = DOCUMENT.read_text(encoding="utf-8")
    self.assertFalse(PDFStructure("1.4", 1).to_dict()["authorizesOpen"])
    self.assertFalse(
      PDFStructureParseFailure(PDFStructureFailureCode.invalidStructure)
      .to_dict()["authorizesOpen"]
    )
    for phrase in (
      "authorizesOpen: false",
      "not an antivirus scan",
      "does not detect all malware",
      "not cryptographically verified",
      "incremental revision",
      "cross-reference streams and object streams",
      "password-protected",
      "not a guarantee",
      "no execution deadline",
      "incomplete/blocked",
      "not a clean result",
    ):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase, text)

  def test_inactive_stage_cannot_replace_scanner_and_user_handoff(self):
    text = DOCUMENT.read_text(encoding="utf-8")
    scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
    self.assertNotIn("pdf_structure_parser", scanner)
    for phrase in (
      "Only the installed Built-in ClamAV scan gate is active",
      "not selectable",
      "not active",
      "signature freshness",
      "file-integrity",
      "quarantine",
      "cache",
      "selected",
      "must not be interpreted as safe",
    ):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase, text)


if __name__ == "__main__":
  unittest.main()
