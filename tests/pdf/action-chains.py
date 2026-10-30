#!/usr/bin/env python3
"""opener-0449: classify unusual/contradictory PDF action /Next chains."""

import builtins
from dataclasses import FrozenInstanceError
from io import BytesIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject, DictionaryObject, NameObject, NumberObject, TextStringObject,
)

from pdf_action_chains import (
    MAX_CHAIN_WIDTH, PDFActionChainInspection, PDFActionChainInspectionError,
    inspect_pdf_action_chains,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parent
_ERROR = "PDF action chains could not be fully inspected; opening was stopped."


def writer_with_page():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    return writer


def pdf(writer):
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def action(kind, next_action=None):
    result = DictionaryObject({NameObject("/S"): NameObject("/" + kind)})
    if next_action is not None:
        result[NameObject("/Next")] = next_action
    return result


def inspect_open_action(first):
    writer = writer_with_page()
    writer._root_object[NameObject("/OpenAction")] = writer._add_object(first)
    return inspect_pdf_action_chains(pdf(writer))


class PDFActionChainTests(unittest.TestCase):
    def test_reference_pdfs_and_unchained_actions_have_no_findings(self):
        for sample in REFERENCE_PDFS:
            with self.subTest(sample=sample.identifier):
                result = inspect_pdf_action_chains(sample.content)
                self.assertEqual(result, PDFActionChainInspection(0, ()))
                self.assertFalse(result.has_unusual_chains)
                self.assertFalse(result.permits_open)
        result = inspect_open_action(action("GoTo"))
        self.assertEqual(result, PDFActionChainInspection(0, ()))

    def test_ordinary_next_chain_and_outline_links_not_misclassified(self):
        writer = writer_with_page()
        chain = action("Named", writer._add_object(action("URI")))
        writer._root_object[NameObject("/OpenAction")] = writer._add_object(chain)
        writer._root_object[NameObject("/Outlines")] = DictionaryObject({
            NameObject("/Next"): DictionaryObject({
                NameObject("/Title"): TextStringObject("ordinary outline"),
            }),
        })
        result = inspect_pdf_action_chains(pdf(writer))
        self.assertEqual(result, PDFActionChainInspection(1, ()))

    def test_competing_navigation_in_linked_actions_and_array(self):
        for next_action in (
            action("GoToR"),
            ArrayObject([action("URI"), action("GoToR")]),
            action("GoTo"),
        ):
            with self.subTest(shape=type(next_action).__name__):
                result = inspect_open_action(action("GoTo", next_action))
                self.assertIn("competing_navigation", result.finding_codes)
                self.assertTrue(result.has_unusual_chains)
                self.assertFalse(result.permits_open)
        single = inspect_open_action(action("GoTo", action("URI")))
        self.assertNotIn("competing_navigation", single.finding_codes)

    def test_conflicting_form_operations_in_array_and_chain(self):
        for next_action in (
            action("ResetForm"),
            ArrayObject([action("ResetForm"), action("ImportData")]),
        ):
            result = inspect_open_action(action("SubmitForm", next_action))
            self.assertIn("conflicting_form_operations", result.finding_codes)
        legitimate = inspect_open_action(action("SubmitForm", action("URI")))
        self.assertNotIn("conflicting_form_operations", legitimate.finding_codes)

    def test_launch_navigation_mixture_does_not_execute_targets(self):
        writer = writer_with_page()
        first = action("Launch", action("GoToR"))
        first[NameObject("/F")] = TextStringObject("PRIVATE-LAUNCH-TARGET")
        writer._root_object[NameObject("/OpenAction")] = writer._add_object(first)
        result = inspect_pdf_action_chains(pdf(writer))
        self.assertIn("mixed_launch_navigation", result.finding_codes)
        self.assertNotIn("PRIVATE-LAUNCH-TARGET", repr(result))
        self.assertNotIn("PRIVATE-LAUNCH-TARGET", json.dumps(result.to_dict()))

    def test_cycle_and_repeated_action_links_are_detected(self):
        writer = writer_with_page()
        first = writer._add_object(action("Named"))
        second = writer._add_object(action("URI"))
        first.get_object()[NameObject("/Next")] = second
        second.get_object()[NameObject("/Next")] = first
        writer._root_object[NameObject("/OpenAction")] = first
        cycle = inspect_pdf_action_chains(pdf(writer))
        self.assertIn("cycle", cycle.finding_codes)

        writer = writer_with_page()
        reused = writer._add_object(action("URI"))
        chain = action("Named", ArrayObject([reused, reused]))
        writer._root_object[NameObject("/OpenAction")] = writer._add_object(chain)
        repeated = inspect_pdf_action_chains(pdf(writer))
        self.assertIn("repeated_action", repeated.finding_codes)
        self.assertNotIn("cycle", repeated.finding_codes)

    def test_deep_wide_and_orphaned_action_chains(self):
        chain = action("URI")
        for _ in range(9):
            chain = action("Named", chain)
        self.assertIn("deep_chain", inspect_open_action(chain).finding_codes)
        wide = action("Named", ArrayObject([
            action("URI") for _ in range(9)
        ]))
        self.assertIn("wide_chain", inspect_open_action(wide).finding_codes)

        writer = writer_with_page()
        writer._add_object(action("GoTo", action("GoToR")))
        orphan = inspect_pdf_action_chains(pdf(writer))
        self.assertIn("competing_navigation", orphan.finding_codes)
        self.assertEqual(orphan.chain_count, 1)

    def test_malformed_next_and_excessive_fanout_fail_closed(self):
        bad = (
            NumberObject(19),
            ArrayObject(),
            ArrayObject([action("Named"), NumberObject(17)]),
            ArrayObject([action("URI") for _ in range(MAX_CHAIN_WIDTH + 1)]),
            DictionaryObject({NameObject("/URI"): TextStringObject("private")}),
        )
        for next_action in bad:
            with self.subTest(kind=type(next_action).__name__, size=len(next_action) if isinstance(next_action, ArrayObject) else None):
                self.assert_rejected(pdf_with_action=action("Named", next_action))
        malformed = action("Named", action("URI"))
        malformed[NameObject("/Next")][NameObject("/S")] = NumberObject(9)
        self.assert_rejected(pdf_with_action=malformed)

    def assert_rejected(self, pdf_with_action=None, raw=None):
        if pdf_with_action is not None:
            raw = pdf_action(pdf_with_action)
        with self.assertRaises(PDFActionChainInspectionError) as raised:
            inspect_pdf_action_chains(raw)
        self.assertEqual(str(raised.exception), _ERROR)
        self.assertNotIn("private", str(raised.exception))

    def test_invalid_encrypted_oversize_and_missing_dependency_fail_closed(self):
        writer = writer_with_page()
        writer.encrypt("private-password")
        for data in (pdf(writer), b"junk", b"%PDF-1.5\n%%EOF\n", None,
                     "not bytes", bytearray(b"pdf"),
                     b"x" * (16 * 1024 * 1024 + 1)):
            with self.subTest(kind=type(data).__name__):
                self.assert_rejected(raw=data)
        imported = builtins.__import__

        def block_import(name, *args, **kwargs):
            if name == "pypdf":
                raise ImportError("private dependency path")
            return imported(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=block_import):
            self.assert_rejected(raw=REFERENCE_PDFS[0].content)

    def test_immutable_sanitized_json_and_no_open_permission(self):
        evidence = PDFActionChainInspection(2, ("cycle", "wide_chain"))
        self.assertTrue(evidence.has_unusual_chains)
        self.assertEqual(evidence.to_dict(), {
            "schemaVersion": 1, "chainCount": 2,
            "findingCodes": ["cycle", "wide_chain"], "authorizesOpen": False,
        })
        report = evidence.to_dict()
        report["findingCodes"].append("fake")
        report["authorizesOpen"] = True
        self.assertEqual(evidence.finding_codes, ("cycle", "wide_chain"))
        self.assertIs(evidence.to_dict()["authorizesOpen"], False)
        with self.assertRaises(FrozenInstanceError):
            evidence.chain_count = 99
        for count, codes in (
            (-1, ()), (513, ()), (True, ()), (0, ("unknown",)),
            (0, ("cycle", "cycle")), (0, ("wide_chain", "cycle")),
            (0, ["cycle"]),
        ):
            with self.subTest(count=count, codes=codes):
                with self.assertRaises(ValueError):
                    PDFActionChainInspection(count, codes)
        with self.assertRaises(TypeError):
            PDFActionChainInspection(0, (), True)

    def test_scanner_and_preferences_remain_unmodified(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        policy = (ROOT / "effective_protection_policy.py").read_text(encoding="utf-8")
        source = (ROOT / "pdf_action_chains.py").read_text(encoding="utf-8")
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertNotIn("pdf_action_chains", scanner)
        self.assertNotIn("pdf_action_chains", policy)
        self.assertIn("python3 scripts/run-test.py tests/pdf/action-chains.py -v", ci)
        for forbidden in ("subprocess.", "launch_clean_file(",
                          "remove_quarantine(", "write_text(", "get_data(",
                          "UserDefaults", "os.environ", "eval(", "exec("):
            self.assertNotIn(forbidden, source)


def pdf_action(entry):
    writer = writer_with_page()
    writer._root_object[NameObject("/OpenAction")] = writer._add_object(entry)
    return pdf(writer)


if __name__ == "__main__":
    unittest.main()
