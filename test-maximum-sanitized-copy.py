#!/usr/bin/env python3
"""Opt-in Maximum sanitized-copy offer and native raster conversion regressions."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject
import maximum_sanitized_copy as copies


def sample_pdf(*, with_actions=False):
    writer = PdfWriter()
    writer.add_blank_page(width=180, height=250)
    if with_actions:
        writer.add_js("app.alert('untrusted');")
        writer.add_attachment("secret payload.txt", b"NEVER COPY THIS SECRET")
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


class SanitizedCopyOfferContractTests(unittest.TestCase):
    def test_invalid_source_never_invokes_converter(self):
        invalid = (b"", "not bytes", bytearray(sample_pdf()), b"not a PDF",
                   b"%PDF" * (copies.MAX_SOURCE_BYTES // 4 + 1))
        with patch.object(copies, "_trusted_converter", return_value=Path("/usr/bin/true")), \
                patch.object(copies, "run_limited_converter") as invoked:
            for item in invalid:
                with self.subTest(type=type(item).__name__):
                    self.assertIsNone(copies.offer_sanitized_pdf_copy(item))
            invoked.assert_not_called()

    def test_unavailable_converter_never_produces_offer_or_launch(self):
        with patch.object(copies, "_trusted_converter", return_value=None), \
                patch.object(copies, "run_limited_converter") as invoked:
            self.assertIsNone(copies.offer_sanitized_pdf_copy(sample_pdf()))
            invoked.assert_not_called()

    def test_encrypted_or_malformed_sources_never_offer_conversion(self):
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.encrypt("secret")
        stream = BytesIO()
        writer.write(stream)
        with patch.object(copies, "_trusted_converter", return_value=Path("/usr/bin/true")), \
                patch.object(copies, "run_limited_converter") as invoked:
            self.assertIsNone(copies.offer_sanitized_pdf_copy(stream.getvalue()))
            self.assertIsNone(copies.offer_sanitized_pdf_copy(b"%PDF-1.7\nbroken"))
            invoked.assert_not_called()

    def test_non_right_angle_rotation_fails_before_converter(self):
        writer = PdfWriter()
        page = writer.add_blank_page(width=180, height=250)
        page[NameObject("/Rotate")] = NumberObject(45)
        stream = BytesIO()
        writer.write(stream)
        with patch.object(copies, "_trusted_converter", return_value=Path("/usr/bin/true")), \
                patch.object(copies, "run_limited_converter") as invoked:
            attempt = copies.attempt_sanitized_pdf_copy(stream.getvalue())
        self.assertIsNone(attempt.offer)
        self.assertEqual(attempt.failure.kind, copies.SanitizerFailureKind.UNSUPPORTED_INPUT)
        invoked.assert_not_called()

    def test_only_verified_completed_conversion_is_offered(self):
        original = sample_pdf()
        different = sample_pdf(with_actions=True)
        scenarios = (subprocess.CompletedProcess([], 7, different),
                     subprocess.CompletedProcess([], 0, b""),
                     subprocess.CompletedProcess([], 0, original),
                     subprocess.CompletedProcess([], 0, b"x" * (copies.MAX_OUTPUT_BYTES + 1)),
                     subprocess.CompletedProcess([], 0, b"not pdf"))
        with patch.object(copies, "_trusted_converter", return_value=Path("/usr/bin/true")):
            for result in scenarios:
                with self.subTest(result=result.returncode, size=len(result.stdout)), \
                        patch.object(copies, "run_limited_converter", return_value=result):
                    self.assertIsNone(copies.offer_sanitized_pdf_copy(original))
            with patch.object(copies, "run_limited_converter",
                              return_value=subprocess.CompletedProcess([], 0, different)), \
                    patch.object(copies, "_passive_pages", return_value=True), \
                    patch.object(copies, "remove_active_pdf_functionality",
                                 return_value=different), \
                    patch.object(copies, "verify_sanitized_pdf_structure") as verify:
                verify.return_value.page_count = 1
                offer = copies.offer_sanitized_pdf_copy(original)
        self.assertIsNotNone(offer)
        self.assertEqual(offer.pdf_bytes, different)
        self.assertEqual(offer.page_count, 1)
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.needs_separate_scan)
        self.assertTrue(offer.rasterized)
        with self.assertRaises(FrozenInstanceError):
            offer.permits_open = True
        with self.assertRaises(ValueError):
            copies.SanitizedCopyOffer(original, 1, permits_open=True)
        with self.assertRaises(ValueError):
            copies.SanitizedCopyOffer(original, 1, needs_separate_scan=False)

    def test_timeout_and_process_error_fail_to_offer_without_disclosure(self):
        original = sample_pdf()
        with patch.object(copies, "_trusted_converter", return_value=Path("/usr/bin/true")):
            for error in (OSError("/private/secret/path"),
                          copies.SanitizerProcessTimedOut("private path")):
                with self.subTest(type=type(error).__name__), \
                        patch.object(copies, "run_limited_converter", side_effect=error):
                    self.assertIsNone(copies.offer_sanitized_pdf_copy(original))

    def test_spawn_is_noninteractive_without_original_path_or_shell(self):
        original = sample_pdf()
        with patch.object(copies, "_trusted_converter", return_value=Path("/usr/bin/true")), \
                patch.object(copies, "run_limited_converter",
                             return_value=subprocess.CompletedProcess([], 0, b"%PDF-different")) as invoked:
            self.assertIsNone(copies.offer_sanitized_pdf_copy(original))
        args, kwargs = invoked.call_args
        self.assertEqual(args[0], ("/usr/bin/true",))
        self.assertIs(args[1], original)
        self.assertEqual(kwargs["timeout_seconds"], copies.CONVERSION_TIMEOUT_SECONDS)
        self.assertEqual(kwargs["max_output_bytes"], copies.MAX_OUTPUT_BYTES)
        self.assertEqual(kwargs["environment"], {
            "PATH": "/usr/bin:/bin", "HOME": "/var/empty",
            "LANG": "C", "PYTHONDONTWRITEBYTECODE": "1",
        })
        self.assertNotIn("HTTP_PROXY", kwargs["environment"])

    def test_action_bearing_pdf_is_not_mistaken_for_passive_output(self):
        source = sample_pdf(with_actions=True)
        self.assertFalse(copies._passive_pages(source, 1))
        self.assertFalse(copies._passive_pages(b"untrusted", 1))
        self.assertFalse(copies._passive_pages(source, 2))

    def test_installed_scan_gate_and_profile_remain_unchanged(self):
        root = Path(__file__).resolve().parent
        scanner = (root / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("maximum_sanitized_copy", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        from protection_profiles import ProtectionProfileID, PROTECTION_PROFILES
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)


@unittest.skipUnless(sys.platform == "darwin", "Real CoreGraphics conversion requires macOS")
class NativeRasterizationTests(unittest.TestCase):
    def test_source_javascript_and_attachment_not_copied_to_raster_pdf(self):
        source = sample_pdf(with_actions=True)
        offer = copies.offer_sanitized_pdf_copy(source)
        self.assertIsNotNone(offer, "Supported PDF pages should yield a verified copy offer")
        self.assertTrue(offer.pdf_bytes.startswith(b"%PDF-"))
        self.assertNotEqual(offer.pdf_bytes, source)
        reader = PdfReader(BytesIO(offer.pdf_bytes), strict=True)
        self.assertEqual(len(reader.pages), 1)
        self.assertEqual(set(reader.trailer["/Root"]), {"/Type", "/Pages"})
        self.assertNotIn("/Names", reader.trailer["/Root"])
        self.assertNotIn("/OpenAction", reader.trailer["/Root"])
        self.assertNotIn("/Annots", reader.pages[0])
        self.assertEqual(set(reader.pages[0]),
                         {"/Type", "/Parent", "/MediaBox", "/Resources", "/Contents"})
        self.assertNotIn(b"NEVER COPY THIS SECRET", offer.pdf_bytes)
        self.assertNotIn(b"app.alert", offer.pdf_bytes)
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.needs_separate_scan)

    def test_debug_page_geometry_path(self):
        source_bytes = sample_pdf()
        converter = copies._trusted_converter()
        original = PdfReader(BytesIO(source_bytes), strict=True)
        geometry = tuple(copies._page_geometry(page) for page in original.pages)
        converted = copies.run_limited_converter(
            (str(converter),), source_bytes,
            timeout_seconds=copies.CONVERSION_TIMEOUT_SECONDS,
            max_output_bytes=copies.MAX_OUTPUT_BYTES,
            environment={"PATH": "/usr/bin:/bin", "HOME": "/var/empty",
                         "LANG": "C", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        rendered = PdfReader(BytesIO(converted.stdout), strict=True)
        print("DEBUG source geometry", geometry)
        print("DEBUG rendered geometry", [
            (float(page.mediabox.width), float(page.mediabox.height),
             repr(page.get_inherited("/Rotate")), repr(page.cropbox),
             repr(page.mediabox), copies._page_geometry(page))
            for page in rendered.pages
        ])
        import maximum_active_content_removal as removal
        print("DEBUG rebuild without expected geometry",
              removal.remove_active_pdf_functionality(converted.stdout, 1) is not None)
        print("DEBUG rebuild with expected geometry",
              removal.remove_active_pdf_functionality(converted.stdout, 1, geometry) is not None)

    def test_real_conversion_preserves_page_order_dimensions_and_rotation(self):
        expected = (
            (180, 240, 0),
            (200, 260, 90),
            (220, 280, 180),
            (240, 300, 270),
        )
        writer = PdfWriter()
        for width, height, rotation in expected:
            page = writer.add_blank_page(width=width, height=height)
            if rotation:
                page.rotate(rotation)
        stream = BytesIO()
        writer.write(stream)

        source = PdfReader(BytesIO(stream.getvalue()), strict=True)
        source_geometry = [
            (float(page.mediabox.width), float(page.mediabox.height),
             int(page.get_inherited("/Rotate") or 0) % 360)
            for page in source.pages
        ]
        self.assertEqual(source_geometry, [tuple(item) for item in expected])

        offer = copies.offer_sanitized_pdf_copy(stream.getvalue())
        self.assertIsNotNone(offer)
        self.assertEqual(offer.page_count, len(expected))
        self.assertTrue(copies._passive_pages(offer.pdf_bytes, len(expected), source_geometry))
        output = PdfReader(BytesIO(offer.pdf_bytes), strict=True)
        actual_geometry = [
            (float(page.mediabox.width), float(page.mediabox.height),
             int(page.get_inherited("/Rotate") or 0) % 360)
            for page in output.pages
        ]
        self.assertEqual(actual_geometry, source_geometry)


    def test_maximum_page_rendering_resolution_is_capped_per_page(self):
        # Exercise the real CoreGraphics renderer at the largest supported
        # page dimensions, then inspect the *generated image* rather than
        # merely asserting the configured source constant.
        writer = PdfWriter()
        writer.add_blank_page(width=1440, height=1440)
        source = BytesIO()
        writer.write(source)

        offer = copies.offer_sanitized_pdf_copy(source.getvalue())
        self.assertIsNotNone(offer)
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.needs_separate_scan)

        reader = PdfReader(BytesIO(offer.pdf_bytes), strict=True)
        self.assertEqual(len(reader.pages), 1)
        resources = reader.pages[0]["/Resources"].get_object()
        xobjects = resources["/XObject"].get_object()
        images = [
            reference.get_object()
            for reference in xobjects.values()
            if reference.get_object().get("/Subtype") == "/Image"
        ]
        self.assertEqual(len(images), 1)
        image = images[0]
        width = int(image["/Width"])
        height = int(image["/Height"])
        self.assertGreater(width, 0)
        self.assertGreater(height, 0)
        self.assertLessEqual(width, 2048)
        self.assertLessEqual(height, 2048)
        self.assertLessEqual(width * height, 24_000_000)


if __name__ == "__main__":
    unittest.main()
