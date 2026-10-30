#!/usr/bin/env python3
"""opener-0460: automatic external-request evidence from real PDF action hooks."""

import os
import socket
import subprocess
from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject, DictionaryObject, NameObject, NumberObject, TextStringObject,
)

from pdf_automatic_external_requests import (
    MAX_ACTIONS, PDFAutomaticExternalRequestError,
    PDFAutomaticExternalRequests, inspect_pdf_automatic_external_requests,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parents[2]
_ERROR = "Automatic PDF external requests could not be fully inspected; opening was stopped."


def action(kind, key=None, target=None):
    result = DictionaryObject({NameObject("/S"): NameObject("/" + kind)})
    if key is not None:
        result[NameObject("/" + key)] = (
            TextStringObject(target) if type(target) is str else target
        )
    return result


def serialize(writer):
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def sample_writer():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    return writer


class PDFAutomaticExternalRequestTests(unittest.TestCase):
    def inspect(self, writer):
        with (patch.object(socket, "getaddrinfo") as dns,
              patch.object(os, "system") as system,
              patch.object(subprocess, "run") as process):
            result = inspect_pdf_automatic_external_requests(serialize(writer))
        dns.assert_not_called()
        system.assert_not_called()
        process.assert_not_called()
        return result

    def assert_blocked(self, data):
        with self.assertRaises(PDFAutomaticExternalRequestError) as caught:
            inspect_pdf_automatic_external_requests(data)
        self.assertEqual(str(caught.exception), _ERROR)

    def test_reference_pdfs_do_not_authorize_network_or_opening(self):
        for sample in REFERENCE_PDFS:
            with self.subTest(sample=sample.identifier):
                result = inspect_pdf_automatic_external_requests(sample.content)
                self.assertEqual(result, PDFAutomaticExternalRequests(0, 0, 0, (), ()))
                self.assertFalse(result.has_potential_external_requests)
                self.assertFalse(result.authorizes_open)

    def test_document_open_uri_identified_without_contacting_destination(self):
        writer = sample_writer()
        writer._root_object[NameObject("/OpenAction")] = writer._add_object(
            action("URI", "URI", "https://private.example.invalid/path?token=secret")
        )
        result = self.inspect(writer)
        self.assertEqual(result.startup_request_count, 1)
        self.assertEqual(result.event_request_count, 0)
        self.assertEqual(result.request_kinds, ("uri_action",))
        self.assertEqual(result.trigger_contexts, ("document_open",))
        self.assertTrue(result.has_potential_external_requests)
        self.assertNotIn("secret", repr(result))
        self.assertNotIn("private.example", str(result.to_dict()))
        self.assertIs(result.to_dict()["authorizesOpen"], False)

    def test_page_and_document_events_are_not_claimed_as_unconditional_open(self):
        writer = sample_writer()
        writer._root_object[NameObject("/AA")] = DictionaryObject({
            NameObject("/WC"): action("SubmitForm", "F", "https://form.example.invalid"),
        })
        writer.pages[0][NameObject("/AA")] = DictionaryObject({
            NameObject("/O"): action("URI", "URI", "http://portal.example.invalid"),
        })
        result = self.inspect(writer)
        self.assertEqual(result.startup_request_count, 0)
        self.assertEqual(result.event_request_count, 2)
        self.assertEqual(result.request_kinds, ("form_submission", "uri_action"))
        self.assertEqual(result.trigger_contexts, ("document_event", "page_event"))

    def test_click_only_links_and_unreferenced_actions_are_not_automatic(self):
        writer = sample_writer()
        link = DictionaryObject({
            NameObject("/Subtype"): NameObject("/Link"),
            NameObject("/A"): action("URI", "URI", "https://clicked.example.invalid"),
        })
        writer.pages[0][NameObject("/Annots")] = ArrayObject([
            writer._add_object(link)
        ])
        writer._add_object(action("URI", "URI", "https://orphan.example.invalid"))
        result = self.inspect(writer)
        self.assertEqual(result, PDFAutomaticExternalRequests(0, 0, 0, (), ()))

    def test_annotation_and_field_events_are_not_mistaken_for_click_only_links(self):
        writer = sample_writer()
        annotation = DictionaryObject({
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/AA"): DictionaryObject({
                NameObject("/E"): action("URI", "URI", "https://hover.example.invalid"),
            }),
        })
        writer.pages[0][NameObject("/Annots")] = ArrayObject([
            writer._add_object(annotation)
        ])
        field = DictionaryObject({
            NameObject("/FT"): NameObject("/Tx"),
            NameObject("/AA"): DictionaryObject({
                NameObject("/K"): action("SubmitForm", "F", "https://form.example.invalid"),
            }),
        })
        writer._root_object[NameObject("/AcroForm")] = DictionaryObject({
            NameObject("/Fields"): ArrayObject([writer._add_object(field)]),
        })
        result = self.inspect(writer)
        self.assertEqual(result.event_request_count, 2)
        self.assertEqual(result.trigger_contexts, ("annotation_event", "field_event"))

    def test_next_arrays_remote_documents_and_network_filespecs(self):
        writer = sample_writer()
        url_file = DictionaryObject({
            NameObject("/FS"): NameObject("/URL"),
            NameObject("/F"): TextStringObject("https://remote.example.invalid/report.pdf"),
        })
        starting = action("Named", "N", NameObject("/NextPage"))
        starting[NameObject("/Next")] = ArrayObject([
            action("GoToR", "F", writer._add_object(url_file)),
            action("ImportData", "F", "https://remote.example.invalid/form.fdf"),
            action("Launch", "F", "https://remote.example.invalid/help"),
        ])
        writer._root_object[NameObject("/OpenAction")] = writer._add_object(starting)
        result = self.inspect(writer)
        self.assertEqual(result.startup_request_count, 3)
        self.assertEqual(result.request_kinds,
                         ("form_import", "launch_url", "remote_document"))
        self.assertFalse(result.authorizes_open)

    def test_local_targets_not_claimed_as_external_network_requests(self):
        writer = sample_writer()
        local = action("GoToR", "F", "local.pdf")
        local[NameObject("/Next")] = ArrayObject([
            action("Launch", "F", "file.txt"),
            action("ImportData", "F", "form.fdf"),
            action("GoToE", "F", "local.pdf"),
        ])
        writer._root_object[NameObject("/OpenAction")] = local
        self.assertEqual(self.inspect(writer), PDFAutomaticExternalRequests(0, 0, 0, (), ()))

    def test_automatic_javascript_counted_as_unassessed_not_confirmed_request(self):
        writer = sample_writer()
        js = action("JavaScript", "JS",
                    "app.launchURL('https://private.example.invalid/secret')")
        js[NameObject("/Next")] = action(
            "URI", "URI", "https://actual.example.invalid"
        )
        writer._root_object[NameObject("/OpenAction")] = writer._add_object(js)
        result = self.inspect(writer)
        self.assertEqual((result.startup_request_count, result.unassessed_script_count), (1, 1))
        self.assertEqual(result.request_kinds, ("uri_action",))
        self.assertNotIn("private.example", repr(result))
        self.assertNotIn("private.example", str(result.to_dict()))

    def test_invalid_targets_and_cycles_fail_closed(self):
        for entry in (
            action("URI"),
            action("URI", "URI", NumberObject(3)),
            action("SubmitForm"),
            action("GoToR"),
            action("URI", "URI", "https://"),
            action("URI", "URI", "https://example.invalid\nprivate"),
            action("JavaScript"),
        ):
            with self.subTest(action=str(entry.get("/S"))):
                writer = sample_writer()
                writer._root_object[NameObject("/OpenAction")] = writer._add_object(entry)
                self.assert_blocked(serialize(writer))
        writer = sample_writer()
        first = writer._add_object(action("Named", "N", NameObject("/NextPage")))
        first.get_object()[NameObject("/Next")] = first
        writer._root_object[NameObject("/OpenAction")] = first
        self.assert_blocked(serialize(writer))

        writer = sample_writer()
        start = action("Named", "N", NameObject("/NextPage"))
        start[NameObject("/Next")] = ArrayObject([
            action("URI", "URI", "https://example.invalid") for _ in range(MAX_ACTIONS + 1)
        ])
        writer._root_object[NameObject("/OpenAction")] = start
        self.assert_blocked(serialize(writer))

    def test_encryption_bad_input_and_missing_dependency_fail_closed(self):
        writer = sample_writer()
        writer.encrypt("test-fixture-password")
        for invalid in (serialize(writer), b"not a pdf", None, b"%PDF-1.4\n%%EOF\n",
                        b"x" * (16 * 1024 * 1024 + 1)):
            with self.subTest(type=type(invalid).__name__):
                self.assert_blocked(invalid)

    def test_immutable_records_never_grant_opening(self):
        result = PDFAutomaticExternalRequests(
            1, 1, 0, ("form_submission", "uri_action"),
            ("document_open", "field_event"),
        )
        copied = result.to_dict()
        copied["requestKinds"].append("fake")
        copied["authorizesOpen"] = True
        self.assertEqual(len(result.request_kinds), 2)
        self.assertFalse(result.to_dict()["authorizesOpen"])
        with self.assertRaises(FrozenInstanceError):
            result.startup_request_count = 5
        for args in (
            (True, 0, 0, (), ()),
            (1, 0, 0, (), ()),
            (0, 0, 0, ("uri_action",), ()),
            (0, 0, 0, (), ("wrong",)),
            (0, 0, 0, ("unknown",), ()),
            (0, 0, 0, ["uri_action"], ()),
        ):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    PDFAutomaticExternalRequests(*args)

    def test_no_change_to_installed_scanner_or_preferences(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        source = (ROOT / "pdf_automatic_external_requests.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/consolidated-checks.yml").read_text(encoding="utf-8")
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertNotIn("pdf_automatic_external_requests", scanner)
        self.assertIn("tests/pdf/automatic-external-requests.py -v", workflow)
        for forbidden in (
            "subprocess.run(", "socket.getaddrinfo(", "requests.get(",
            "write_text(", "launch_clean_file(", "remove_quarantine(",
            "os.environ", "eval(", "exec(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
