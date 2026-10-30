#!/usr/bin/env python3
"""opener-0287: inspect inert JavaScript action payloads in real PDFs."""

import builtins
from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import zlib
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject, ByteStringObject, DecodedStreamObject, DictionaryObject,
    EncodedStreamObject, NameObject, TextStringObject,
)
from pdf_javascript_actions import (
    MAX_SCRIPT_BYTES, MAX_JAVASCRIPT_ACTIONS, PDFJavaScriptInspection,
    PDFJavaScriptInspectionError, _decode_script, inspect_pdf_javascript_actions,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parent


def document(writer):
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def sample_writer():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    return writer


def javascript_action(payload):
    return DictionaryObject({
        NameObject("/S"): NameObject("/JavaScript"),
        NameObject("/JS"): payload,
    })


def inspected_open_action(payload):
    writer = sample_writer()
    writer._root_object[NameObject("/OpenAction")] = writer._add_object(
        javascript_action(payload)
    )
    return inspect_pdf_javascript_actions(document(writer))


class PDFJavaScriptActionTests(unittest.TestCase):
    def test_reference_pdfs_report_no_scripts_but_cannot_approve_opening(self):
        for sample in REFERENCE_PDFS:
            with self.subTest(sample=sample.identifier):
                result = inspect_pdf_javascript_actions(sample.content)
                self.assertEqual(result, PDFJavaScriptInspection(
                    0, 0, (), (), ()
                ))
                self.assertFalse(result.contains_javascript)
                self.assertFalse(result.permits_open)
                with self.assertRaises(FrozenInstanceError):
                    result.action_count = 1

    def test_open_action_inspects_script_bytes_without_executing_it(self):
        # A Python exception would escape if the PDF's JS were run as code.
        script = "app.launchURL('https://sensitive.invalid'); eval('secret');"
        result = inspected_open_action(TextStringObject(script))
        self.assertEqual(result.action_count, 1)
        self.assertEqual(result.total_script_bytes, len(script.encode("utf-8")))
        self.assertEqual(result.trigger_types, ("document_open",))
        self.assertEqual(result.payload_types, ("text",))
        self.assertEqual(result.api_reference_hints, (
            "dynamic_execution", "network"
        ))
        self.assertTrue(result.contains_javascript)
        self.assertFalse(result.permits_open)
        self.assertNotIn(script, repr(result))
        self.assertNotIn("sensitive", repr(result))

    def test_indirect_name_tree_chains_are_inspected_without_script_text(self):
        writer = sample_writer()
        first = javascript_action(TextStringObject("this.submitForm('private')"))
        first[NameObject("/Next")] = writer._add_object(
            javascript_action(TextStringObject("this.exportDataObject('private')"))
        )
        leaf = DictionaryObject({
            NameObject("/Names"): ArrayObject([
                TextStringObject("script name"),
                writer._add_object(first),
            ])
        })
        writer._root_object[NameObject("/Names")] = DictionaryObject({
            NameObject("/JavaScript"): DictionaryObject({
                NameObject("/Kids"): ArrayObject([writer._add_object(leaf)])
            }),
        })
        result = inspect_pdf_javascript_actions(document(writer))
        self.assertEqual(result.action_count, 2)
        self.assertEqual(result.trigger_types, ("document_javascript",))
        self.assertEqual(result.api_reference_hints, ("file_access", "network"))
        self.assertFalse(result.permits_open)

    def test_page_annotation_and_field_hooks_reuse_complete_action_walk(self):
        writer = sample_writer()
        writer.pages[0][NameObject("/AA")] = DictionaryObject({
            NameObject("/O"): javascript_action(TextStringObject("app.alert('one')"))
        })
        annotation = DictionaryObject({
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/AA"): DictionaryObject({
                NameObject("/E"): javascript_action(TextStringObject("eval('x')")),
            }),
        })
        writer.pages[0][NameObject("/Annots")] = ArrayObject([
            writer._add_object(annotation)
        ])
        field = DictionaryObject({
            NameObject("/FT"): NameObject("/Tx"),
            NameObject("/AA"): DictionaryObject({
                NameObject("/K"): javascript_action(TextStringObject("app.getURL('x')")),
            }),
        })
        writer._root_object[NameObject("/AcroForm")] = DictionaryObject({
            NameObject("/Fields"): ArrayObject([writer._add_object(field)])
        })
        result = inspect_pdf_javascript_actions(document(writer))
        self.assertEqual(result.action_count, 3)
        self.assertEqual(result.trigger_types, (
            "annotation_additional", "field_additional", "page_additional"
        ))
        self.assertEqual(result.api_reference_hints, (
            "dynamic_execution", "network"
        ))

    def test_byte_strings_and_raw_streams_are_inspected(self):
        # pypdf normalizes valid serialized PDF byte strings to Unicode.
        for payload in (
            ByteStringObject(b"app.alert('bytes')"),
            ByteStringObject(b"\xfe\xff" + "app.alert('utf16')".encode("utf-16-be")),
        ):
            with self.subTest(payload=bytes(payload)[:6]):
                result = inspected_open_action(payload)
                self.assertEqual(result.payload_types, ("text",))
                self.assertEqual(result.action_count, 1)
        # Raw ByteStringObject inspection is also covered, without round-trip.
        from pypdf.generic import StreamObject
        text, size, kind = _decode_script(
            ByteStringObject(b"app.alert('raw')"),
            TextStringObject, ByteStringObject, StreamObject, NameObject,
        )
        self.assertEqual((text, size, kind),
                         ("app.alert('raw')", len(b"app.alert('raw')"), "bytes"))
        writer = sample_writer()
        stream = DecodedStreamObject()
        stream.set_data(b"app.alert('inert stream')")
        writer._root_object[NameObject("/OpenAction")] = writer._add_object(
            javascript_action(writer._add_object(stream))
        )
        result = inspect_pdf_javascript_actions(document(writer))
        self.assertEqual(result.action_count, 1)
        self.assertEqual(result.payload_types, ("stream",))

    def test_single_flate_stream_is_decoded_under_size_limit(self):
        writer = sample_writer()
        stream = EncodedStreamObject()
        plain = b"app.launchURL('https://example.invalid')"
        stream._data = zlib.compress(plain)
        stream[NameObject("/Filter")] = NameObject("/FlateDecode")
        writer._root_object[NameObject("/OpenAction")] = writer._add_object(
            javascript_action(writer._add_object(stream))
        )
        result = inspect_pdf_javascript_actions(document(writer))
        self.assertEqual(result.payload_types, ("stream",))
        self.assertEqual(result.total_script_bytes, len(plain))
        self.assertEqual(result.api_reference_hints, ("network",))

    def test_unsupported_stream_filters_or_expansion_fail_closed(self):
        for compressed, filter_name in (
            (zlib.compress(b"A" * (MAX_SCRIPT_BYTES + 1)), "/FlateDecode"),
            (b"012345", "/ASCII85Decode"),
            (b"not-valid-compressed-bytes", "/FlateDecode"),
        ):
            with self.subTest(codec=filter_name, length=len(compressed)):
                writer = sample_writer()
                stream = EncodedStreamObject()
                stream._data = compressed
                stream[NameObject("/Filter")] = NameObject(filter_name)
                writer._root_object[NameObject("/OpenAction")] = writer._add_object(
                    javascript_action(writer._add_object(stream))
                )
                with self.assertRaises(PDFJavaScriptInspectionError) as blocked:
                    inspect_pdf_javascript_actions(document(writer))
                self.assertEqual(str(blocked.exception),
                                 "PDF JavaScript actions could not be fully inspected; opening was stopped.")

    def test_empty_invalid_or_oversized_scripts_fail_closed(self):
        cases = (
            TextStringObject(""),
            TextStringObject("A" * (MAX_SCRIPT_BYTES + 1)),
            ByteStringObject(b"console.log('x')\x00"),
        )
        for payload in cases:
            with self.subTest(kind=type(payload).__name__, size=len(payload)):
                with self.assertRaises(PDFJavaScriptInspectionError):
                    inspected_open_action(payload)
        # PDFDocEncoding can normalize these bytes during a PDF round-trip,
        # so exercise strict raw-byte decoding directly.
        from pypdf.generic import StreamObject
        with self.assertRaises(PDFJavaScriptInspectionError):
            _decode_script(ByteStringObject(b"\xff\xff\xff"),
                           TextStringObject, ByteStringObject, StreamObject, NameObject)

    def test_script_count_limit_is_enforced_through_next_action_arrays(self):
        writer = sample_writer()
        parent = javascript_action(TextStringObject("app.alert('root')"))
        parent[NameObject("/Next")] = ArrayObject([
            writer._add_object(javascript_action(TextStringObject("app.alert('next')")))
            for _ in range(MAX_JAVASCRIPT_ACTIONS)
        ])
        writer._root_object[NameObject("/OpenAction")] = writer._add_object(parent)
        with self.assertRaises(PDFJavaScriptInspectionError):
            inspect_pdf_javascript_actions(document(writer))

    def test_encrypted_malformed_and_unavailable_parser_fail_closed(self):
        writer = sample_writer()
        writer.encrypt("do-not-read-password")
        for contents in (document(writer), b"bad", b"%PDF-1.7\n%%EOF\n", None):
            with self.subTest(contents=type(contents).__name__):
                with self.assertRaises(PDFJavaScriptInspectionError) as error:
                    inspect_pdf_javascript_actions(contents)
                self.assertNotIn("do-not-read-password", str(error.exception))
        original = builtins.__import__
        def missing(name, *args, **kwargs):
            if name == "pypdf.generic":
                raise ModuleNotFoundError("test-only")
            return original(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=missing):
            with self.assertRaises(PDFJavaScriptInspectionError):
                inspect_pdf_javascript_actions(REFERENCE_PDFS[0].content)

    def test_no_scanner_activation_and_ci_registers_the_stage(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        resolver = (ROOT / "effective_protection_policy.py").read_text(encoding="utf-8")
        module = (ROOT / "pdf_javascript_actions.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertNotIn("pdf_javascript_actions", scanner)
        self.assertNotIn("pdf_javascript_actions", resolver)
        for forbidden in ("subprocess.", "launch_clean_file(", "remove_quarantine(",
                          "UserDefaults", "os.environ", "write_text(", "eval(", "exec("):
            self.assertNotIn(forbidden, module)
        self.assertIn("python3 scripts/run-test.py tests/pdf/javascript-actions.py -v", workflow)
        self.assertIn("python3 scripts/run-test.py tests/pdf/automatic-actions.py -v", workflow)


if __name__ == "__main__":
    unittest.main()
