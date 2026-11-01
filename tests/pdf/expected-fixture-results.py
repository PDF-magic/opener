#!/usr/bin/env python3
"""Check every known PDF security fixture has an explicit, nonauthorizing expectation.

Manifest values describe tests, not real malware verdicts or scanner decisions.
The registry test never opens/renders PDFs, runs the live scanner or accesses
fixture contents; in-memory corpus modules are imported only for identifiers.
"""
import importlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tests/fixtures/pdf-security-corpus/expected-results.json"

# Enumerate every currently established corpus independently of the manifest.
# A new fixture in one of these families MUST add an expected-result record.
COLLECTIONS = {
  "reference": ("reference_pdf_collection", "REFERENCE_PDFS", "identifier"),
  "incorrectly-named": ("reference_pdf_collection", "INCORRECTLY_NAMED_FILES", "filename"),
  "invalid-header": ("reference_pdf_collection", "INVALID_PDF_HEADERS", "identifier"),
  "incremental": ("reference_pdf_collection", "INCREMENTAL_REFERENCE_PDFS", "identifier"),
  "malformed-xref": ("malformed_xref_pdf_collection", "MALFORMED_XREF_PDFS", "identifier"),
  "valid-object-stream": ("malformed_object_stream_corpus", "VALID_OBJECT_STREAM_PDFS", "identifier"),
  "malformed-object-stream": ("malformed_object_stream_corpus", "MALFORMED_OBJECT_STREAM_PDFS", "identifier"),
  "encrypted": ("encrypted_pdf_collection", "ENCRYPTED_REFERENCE_PDFS", "identifier"),
  "javascript": ("javascript_action_corpus", "JAVASCRIPT_ACTION_PDFS", "identifier"),
  "external-launch": ("external_launch_action_corpus", "EXTERNAL_LAUNCH_PDFS", "identifier"),
  "embedded-file": ("embedded_file_corpus", "EMBEDDED_FILE_PDFS", "identifier"),
  "interactive-form": ("interactive_form_corpus", "INTERACTIVE_FORM_PDFS", "identifier"),
  "unicode-metadata": ("unicode_metadata_corpus", "UNICODE_METADATA_PDFS", "identifier"),
  "oversized-stream": ("oversized_stream_corpus", "OVERSIZED_STREAM_PDFS", "identifier"),
  "large-valid": ("large_valid_pdf_corpus", "LARGE_VALID_PDF_CASES", "identifier"),
  "memory-stress": ("memory_stress_pdf_corpus", "MEMORY_STRESS_PDFS", "identifier"),
  "deep-reference": ("deep_object_reference_corpus", "SECURITY_REFERENCE_PDFS", "identifier"),
}
TRACKED = {
  "truncated": "tests/fixtures/pdf-security-corpus/truncated",
  "parser-timeout": "tests/fixtures/pdf-security-corpus/parser-timeouts",
  "empty": "tests/fixtures",
}
SIGNED_IDS = {"approval-signature", "certification-docmdp"}


class ExpectedFixtureResultTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.records = json.loads(MANIFEST.read_text(encoding="utf-8"))

  def test_manifest_schema_and_every_record_has_a_specific_safe_result(self):
    self.assertEqual(self.records["schemaVersion"], 1)
    self.assertIn("never scanner authorization", self.records["purpose"])
    observed = set()
    for entry in self.records["fixtures"]:
      with self.subTest(collection=entry.get("collection"), fixture=entry.get("id")):
        self.assertEqual(set(entry), {
          "collection", "id", "expectedResult", "details", "authorizesOpen",
        })
        key = (entry["collection"], entry["id"])
        self.assertNotIn(key, observed, "Duplicate expected result")
        observed.add(key)
        self.assertIs(type(entry["id"]), str)
        self.assertTrue(entry["id"])
        self.assertTrue(entry["expectedResult"])
        self.assertIs(type(entry["details"]), dict)
        self.assertTrue(entry["details"], "An expected result must include evidence")
        self.assertIs(entry["authorizesOpen"], False)
    self.assertGreaterEqual(len(observed), 85)

  def test_each_live_collection_is_fully_and_exclusively_documented(self):
    entries = {}
    for item in self.records["fixtures"]:
      entries.setdefault(item["collection"], set()).add(item["id"])
    self.assertEqual(set(entries), set(COLLECTIONS) | set(TRACKED) | {"digital-signature"})
    for family, (module_name, attribute, identifier) in COLLECTIONS.items():
      cases = getattr(importlib.import_module(module_name), attribute)
      actual = {getattr(case, identifier) for case in cases}
      self.assertEqual(len(actual), len(cases), family)
      with self.subTest(family=family):
        self.assertEqual(entries[family], actual)

    truncated = {p.name for p in (ROOT / TRACKED["truncated"]).glob("*.pdf")}
    empty = {"empty", "empty.pdf", "empty.txt"}
    self.assertEqual(entries["truncated"], truncated)
    self.assertEqual(entries["parser-timeout"],
                     {p.name for p in (ROOT / TRACKED["parser-timeout"]).glob("*.pdf")})
    self.assertEqual(entries["empty"], empty)
    for name in empty:
      self.assertTrue((ROOT / "tests/fixtures" / name).is_file())

    # The signer generates an ephemeral private key only in its dedicated test.
    # Inspect its source identifiers without invoking key generation here.
    signature_source = (ROOT / "digital_signature_corpus.py").read_text(encoding="utf-8")
    self.assertEqual(entries["digital-signature"], SIGNED_IDS)
    for identifier in SIGNED_IDS:
      self.assertIn('"' + identifier + '"', signature_source)

  def test_expectation_details_agree_with_fixture_metadata(self):
    entries = {(item["collection"], item["id"]): item
               for item in self.records["fixtures"]}
    from reference_pdf_collection import (
      REFERENCE_PDFS, INCORRECTLY_NAMED_FILES, INVALID_PDF_HEADERS,
      INCREMENTAL_REFERENCE_PDFS,
    )
    for item in REFERENCE_PDFS:
      recorded = entries["reference", item.identifier]
      self.assertEqual(recorded["details"]["simulatedScannerOutcome"],
                       item.simulated_scanner_outcome)
      self.assertEqual(recorded["expectedResult"], "simulated-scanner-verdict")
    for item in INCREMENTAL_REFERENCE_PDFS:
      self.assertEqual(entries["incremental", item.identifier]["details"]
                       ["simulatedScannerOutcome"], item.simulated_scanner_outcome)
    for item in INCORRECTLY_NAMED_FILES:
      expected = entries["incorrectly-named", item.filename]
      self.assertEqual(expected["details"]["isPdf"], item.is_pdf)
      self.assertEqual(expected["expectedResult"],
                       "pdf-header" if item.is_pdf else "not-pdf")
    for item in INVALID_PDF_HEADERS:
      expected = entries["invalid-header", item.identifier]
      self.assertEqual(expected["details"]["headerStatus"],
                       item.expected_header_status)
      self.assertEqual(expected["expectedResult"],
                       "not-pdf" if item.expected_header_status == "notPdf"
                       else "undetermined")
    for item in importlib.import_module("javascript_action_corpus").JAVASCRIPT_ACTION_PDFS:
      expected = entries["javascript", item.identifier]["details"]
      self.assertEqual(expected["trigger"], item.expected_trigger)
      self.assertEqual(expected["payloadType"], item.expected_payload_type)
      self.assertEqual(expected["hints"], list(item.expected_hints))
    for item in importlib.import_module("external_launch_action_corpus").EXTERNAL_LAUNCH_PDFS:
      expected = entries["external-launch", item.identifier]["details"]
      self.assertEqual(expected["trigger"], item.expected_trigger)
      self.assertEqual(expected["actionCount"], item.expected_actions)
      self.assertEqual(expected["targets"], list(item.expected_targets))
    for item in importlib.import_module("unicode_metadata_corpus").UNICODE_METADATA_PDFS:
      expected = entries["unicode-metadata", item.identifier]["details"]
      self.assertEqual(expected["infoKeys"], sorted(key.lower() for key, _ in item.info))
      self.assertEqual(expected["hasXmp"], bool(item.xmp))
    for item in importlib.import_module("interactive_form_corpus").INTERACTIVE_FORM_PDFS:
      expected = entries["interactive-form", item.identifier]["details"]
      self.assertEqual(expected["fieldType"], item.field_type)
      self.assertEqual(expected["fieldValue"], item.field_value)
    for item in importlib.import_module("embedded_file_corpus").EMBEDDED_FILE_PDFS:
      expected = entries["embedded-file", item.identifier]["details"]
      self.assertEqual(expected["location"], item.location)
      self.assertEqual(expected["attachmentCount"], len(item.attachments))
    for item in importlib.import_module("oversized_stream_corpus").OVERSIZED_STREAM_PDFS:
      expected = entries["oversized-stream", item.identifier]["details"]
      self.assertEqual(tuple(expected[key] for key in
                             ("encoded", "decoded", "highExpansion", "declared")),
                       (item.expected_large_encoded, item.expected_large_decoded,
                        item.expected_high_expansion, item.expected_large_declared))
    for item in importlib.import_module("large_valid_pdf_corpus").LARGE_VALID_PDF_CASES:
      self.assertEqual(entries["large-valid", item.identifier]["details"]["pageCount"],
                       item.page_count)
    for item in importlib.import_module("encrypted_pdf_collection").ENCRYPTED_REFERENCE_PDFS:
      self.assertEqual(entries["encrypted", item.identifier]["details"]["keyBits"],
                       item.key_bits)

  def test_tracked_files_and_ci_are_kept_test_only(self):
    # No sensitive fixture bytes are inspected here.
    for entry in self.records["fixtures"]:
      if "path" in entry["details"]:
        self.assertTrue((ROOT / entry["details"]["path"]).is_file())
    scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
    self.assertNotIn("expected-results.json", scanner)
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    self.assertIn("PYTHONPATH=. python3 tests/pdf/expected-fixture-results.py -v", ci)
    ignore = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    self.assertIn("tests/fixtures/pdf-security-corpus/ export-ignore", ignore)


if __name__ == "__main__":
  unittest.main()
