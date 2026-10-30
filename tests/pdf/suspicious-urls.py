#!/usr/bin/env python3
"""opener-0292: identify suspicious embedded URLs without contacting destinations."""
from dataclasses import FrozenInstanceError
from io import BytesIO
import os
from pathlib import Path
import socket
import subprocess
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import (ArrayObject, ByteStringObject, DictionaryObject,
                           NameObject, TextStringObject)
from pdf_suspicious_urls import (
    BLOCK_MESSAGE, MAX_PDF_BYTES, MAX_URLS, PDFSuspiciousURLInspectionError,
    inspect_pdf_suspicious_urls,
)


def fixture(*urls, location="action"):
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    if location == "action":
        actions = [writer._add_object(DictionaryObject({
            NameObject("/S"): NameObject("/URI"),
            NameObject("/URI"): TextStringObject(url),
        })) for url in urls]
        if actions:
            writer._root_object[NameObject("/OpenAction")] = actions[0]
            if len(actions) > 1:
                actions[0].get_object()[NameObject("/Next")] = ArrayObject(actions[1:])
    elif location == "annotation":
        page[NameObject("/Annots")] = ArrayObject([
            writer._add_object(DictionaryObject({
                NameObject("/Subtype"): NameObject("/Link"),
                NameObject("/A"): DictionaryObject({
                    NameObject("/S"): NameObject("/URI"),
                    NameObject("/URI"): TextStringObject(url),
                }),
            })) for url in urls
        ])
    elif location == "base":
        writer._root_object[NameObject("/URI")] = DictionaryObject({
            NameObject("/Base"): TextStringObject(urls[0]),
        })
    elif location == "orphan":
        for url in urls:
            writer._add_object(DictionaryObject({
                NameObject("/S"): NameObject("/URI"),
                NameObject("/URI"): TextStringObject(url),
            }))
    else:
        raise AssertionError("unknown fixture location")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class PDFSuspiciousURLTests(unittest.TestCase):
    def test_reference_pdfs_have_no_urls_and_no_open_authorization(self):
        from reference_pdf_collection import REFERENCE_PDFS
        for sample in REFERENCE_PDFS:
            with self.subTest(name=sample.identifier):
                result = inspect_pdf_suspicious_urls(sample.content)
                self.assertEqual(result.url_count, 0)
                self.assertFalse(result.has_suspicious_urls)
                self.assertFalse(result.permits_open)
                with self.assertRaises(FrozenInstanceError):
                    result.permits_open = True

    def test_safe_https_links_and_base_are_counted_not_flagged(self):
        for location in ("action", "annotation", "base", "orphan"):
            with self.subTest(location=location):
                result = inspect_pdf_suspicious_urls(
                    fixture("https://example.org/path?q=ok", location=location)
                )
                self.assertEqual(
                    (result.url_count, result.suspicious_count, result.categories),
                    (1, 0, ())
                )

    def test_scheme_host_and_credential_risks_are_classified_without_leaks(self):
        urls = (
            "http://example.org", "javascript:alert(1)",
            "https://user:password@example.org/private", "https://127.0.0.1:8080/",
            "https://localhost/admin", "https://internal.onion/",
            "https://xn--bcher-kva.example/", "https://0x7f000001/path",
            "https://example.org:8443/", "https://example.org/%0d%0aheader",
            "../relative/link", "https://ex%61mple.org/",
        )
        with (patch.object(socket, "getaddrinfo") as dns,
              patch.object(os, "system") as shell,
              patch.object(subprocess, "run") as run):
            result = inspect_pdf_suspicious_urls(fixture(*urls))
        self.assertEqual(result.url_count, len(urls))
        self.assertEqual(result.suspicious_count, len(urls))
        self.assertEqual(result.categories, tuple(sorted((
            "unencrypted_http", "non_web_scheme", "embedded_credentials",
            "non_global_ip", "nonstandard_port", "local_hostname",
            "hidden_service", "internationalized_host", "numeric_host",
            "encoded_control", "relative_reference", "encoded_host",
        ))))
        self.assertNotIn("password", repr(result))
        self.assertNotIn("example.org", repr(result))
        self.assertFalse(result.permits_open)
        dns.assert_not_called()
        shell.assert_not_called()
        run.assert_not_called()

    def test_utf16_and_utf8_bytes_inspected_without_leaking(self):
        from pdf_suspicious_urls import _classify_url
        self.assertEqual(
            _classify_url(ByteStringObject(b"https://example.org")), set()
        )
        self.assertEqual(
            _classify_url(ByteStringObject(
                b"\xfe\xff" + "http://example.org".encode("utf-16-be")
            )),
            {"unencrypted_http"}
        )

    def test_broken_urls_are_uninspectable_not_clean(self):
        samples = (
            "", "https://", "https://[bad/", "https://example.org:999999/",
            "https://example.org\r\nmalicious", "https://example.org\\@evil.test",
            "https://example.org/%zx", " https://example.org",
            "https://example.org\u200b",
        )
        for url in samples:
            with self.subTest(url=repr(url)):
                with self.assertRaises(PDFSuspiciousURLInspectionError) as error:
                    inspect_pdf_suspicious_urls(fixture(url))
                self.assertEqual(str(error.exception), BLOCK_MESSAGE)

    def test_form_url_and_url_filespec_are_counted_without_executing(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        form_action = DictionaryObject({
            NameObject("/S"): NameObject("/SubmitForm"),
            NameObject("/F"): TextStringObject("http://192.168.1.1/submit"),
        })
        writer._root_object[NameObject("/OpenAction")] = writer._add_object(form_action)
        writer._add_object(DictionaryObject({
            NameObject("/Type"): NameObject("/Filespec"),
            NameObject("/FS"): NameObject("/URL"),
            NameObject("/F"): TextStringObject("https://local.internal/data"),
        }))
        output = BytesIO()
        writer.write(output)
        report = inspect_pdf_suspicious_urls(output.getvalue())
        self.assertEqual((report.url_count, report.suspicious_count), (2, 2))
        self.assertIn("non_global_ip", report.categories)
        self.assertIn("local_hostname", report.categories)

    def test_bounded_number_of_urls_fails_closed(self):
        with self.assertRaises(PDFSuspiciousURLInspectionError) as error:
            inspect_pdf_suspicious_urls(
                fixture(*(["https://example.org"] * (MAX_URLS + 1)))
            )
        self.assertEqual(str(error.exception), BLOCK_MESSAGE)

    def test_missing_and_invalid_uri_entries_fail_closed(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer._root_object[NameObject("/OpenAction")] = writer._add_object(
            DictionaryObject({NameObject("/S"): NameObject("/URI")})
        )
        out = BytesIO()
        writer.write(out)
        with self.assertRaises(PDFSuspiciousURLInspectionError):
            inspect_pdf_suspicious_urls(out.getvalue())

    def test_oversize_malformed_and_encrypted_inputs_fail_closed(self):
        samples = (b"", b"garbage", b"%PDF-1.7\ntruncated", "not bytes",
                   b"X" * (MAX_PDF_BYTES + 1))
        for sample in samples:
            with self.subTest(size=len(sample)):
                with self.assertRaises(PDFSuspiciousURLInspectionError) as error:
                    inspect_pdf_suspicious_urls(sample)
                self.assertEqual(str(error.exception), BLOCK_MESSAGE)
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("password")
        out = BytesIO()
        writer.write(out)
        with self.assertRaises(PDFSuspiciousURLInspectionError):
            inspect_pdf_suspicious_urls(out.getvalue())
        with self.assertRaises(PDFSuspiciousURLInspectionError):
            inspect_pdf_suspicious_urls(fixture("https://example.org")[:-15])

    def test_current_scanner_and_preferences_are_not_modified(self):
        root = Path(__file__).resolve().parents[2]
        scanner = (root / "scan-and-open.py").read_text()
        self.assertNotIn("pdf_suspicious_urls", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
