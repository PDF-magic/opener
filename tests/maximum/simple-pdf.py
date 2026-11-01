#!/usr/bin/env python3
"""opener-1018: a simple PDF must not bypass planned Maximum safeguards.

The raster worker result is a deterministic synthetic fixture, not a claim
that Maximum is deployed. Real output rebuilding and structural validation
run unmocked; no viewer, user preferences or antivirus service are touched.
"""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import zlib

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, NumberObject, StreamObject

from effective_protection_policy import (
    ACTIVE_PROFILE_ID, SELECTED_PROFILE_KEY,
    UnsupportedEffectivePolicy, resolve_effective_policy,
)
from protection_policy_definitions import (
    BASELINE_CONTROLS, ControlAvailability, FailureDisposition,
    protection_policy_definition,
)
from protection_profiles import ProtectionProfileID, protection_profile_definition
from reference_pdf_collection import REFERENCE_PDFS
import maximum_sanitized_copy as copies


ROOT = Path(__file__).resolve().parents[2]
SIMPLE = next(item.content for item in REFERENCE_PDFS
              if item.identifier == "clean-basic")


def synthetic_raster_worker_result():
    """Build an actual one-image PDF as the output of a mocked trusted worker."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    image = StreamObject()
    image._data = zlib.compress(bytes((20, 130, 220)) * (24 * 32))
    image.update({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Image"),
        NameObject("/Width"): NumberObject(24),
        NameObject("/Height"): NumberObject(32),
        NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
        NameObject("/BitsPerComponent"): NumberObject(8),
        NameObject("/Filter"): NameObject("/FlateDecode"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/XObject"): DictionaryObject({
            NameObject("/Im0"): writer._add_object(image),
        }),
    })
    content = StreamObject()
    content._data = b"q 612 0 0 792 0 0 cm /Im0 Do Q\n"
    page[NameObject("/Contents")] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class MaximumSimplePDFTests(unittest.TestCase):
    def test_simple_pdf_is_structurally_valid_and_maximum_remains_unavailable(self):
        reader = PdfReader(BytesIO(SIMPLE), strict=True)
        self.assertFalse(reader.is_encrypted)
        self.assertEqual(len(reader.pages), 1)
        self.assertEqual(reader.pages[0].extract_text().strip(), "Clean baseline")

        catalog = protection_profile_definition(ProtectionProfileID.MAXIMUM)
        maximum = protection_policy_definition(ProtectionProfileID.MAXIMUM)
        enhanced = protection_policy_definition(ProtectionProfileID.ENHANCED)
        self.assertEqual(catalog.display_name, "Maximum")
        self.assertFalse(catalog.selectable)
        self.assertFalse(maximum.selectable)
        self.assertIs(maximum.failure_disposition, FailureDisposition.DENY)
        inherited = {item.control: item.availability
                     for item in (*enhanced.requirements, *enhanced.optional_checks)}
        actual = {item.control: item.availability for item in maximum.requirements}
        self.assertEqual(actual, inherited)
        self.assertTrue(all(actual[control] is ControlAvailability.CURRENT
                            for control in BASELINE_CONTROLS))
        self.assertTrue(any(status is ControlAvailability.PLANNED
                            for status in actual.values()))

        self.assertEqual(resolve_effective_policy().profile_id, ACTIVE_PROFILE_ID)
        with patch.object(copies, "run_limited_converter") as converter:
            with self.assertRaises(UnsupportedEffectivePolicy):
                resolve_effective_policy({SELECTED_PROFILE_KEY: "maximum"})
            converter.assert_not_called()

    def test_simple_pdf_rebuild_yields_raster_only_offer_never_an_open_verdict(self):
        source = bytes(SIMPLE)
        raster = synthetic_raster_worker_result()
        self.assertTrue(raster.startswith(b"%PDF-"))
        self.assertFalse(copies._passive_pages(source, 1))
        with (
            patch.object(copies, "_trusted_converter",
                         return_value=Path("/synthetic/trusted-converter")),
            patch.object(copies, "run_limited_converter",
                         return_value=subprocess.CompletedProcess([], 0, raster)) as worker,
        ):
            decision = copies.assess_sanitized_pdf_copy(source)

        worker.assert_called_once()
        args, kwargs = worker.call_args
        self.assertEqual(args[0], ("/synthetic/trusted-converter",))
        self.assertEqual(args[1], source)
        self.assertEqual(kwargs["timeout_seconds"], copies.CONVERSION_TIMEOUT_SECONDS)
        self.assertEqual(kwargs["max_output_bytes"], copies.MAX_OUTPUT_BYTES)
        self.assertEqual(kwargs["environment"], {
            "PATH": "/usr/bin:/bin", "HOME": "/var/empty",
            "LANG": "C", "PYTHONDONTWRITEBYTECODE": "1",
        })
        self.assertEqual(decision.action, "offerForSeparateScan")
        self.assertFalse(decision.permits_open)
        self.assertFalse(decision.allow_clean_cache)
        self.assertTrue(decision.requires_separate_scan)
        self.assertIsNotNone(decision.offer)
        offer = decision.offer
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.needs_separate_scan)
        self.assertTrue(offer.rasterized)
        self.assertFalse(offer.ocr_restored)
        self.assertNotEqual(offer.pdf_bytes, source)
        self.assertNotEqual(offer.pdf_bytes, raster)
        self.assertEqual(source, SIMPLE)

        rebuilt = PdfReader(BytesIO(offer.pdf_bytes), strict=True)
        self.assertEqual(len(rebuilt.pages), 1)
        self.assertEqual(set(rebuilt.trailer["/Root"]), {"/Type", "/Pages"})
        self.assertEqual(float(rebuilt.pages[0].mediabox.width), 612.0)
        self.assertEqual(float(rebuilt.pages[0].mediabox.height), 792.0)
        self.assertEqual(rebuilt.pages[0].extract_text().strip(), "")
        images = list(rebuilt.pages[0].images)
        self.assertEqual(len(images), 1)
        with Image.open(BytesIO(images[0].data)) as image:
            self.assertEqual(image.size, (24, 32))
            self.assertEqual(image.convert("RGB").getpixel((0, 0)), (20, 130, 220))
        self.assertTrue(copies._passive_pages(offer.pdf_bytes, 1))
        metadata = offer.to_public_metadata()
        self.assertTrue(metadata["requiresFreshScan"])
        self.assertFalse(metadata["authorizesOpen"])
        self.assertFalse(metadata["isUntouchedOriginal"])
        with self.assertRaises(FrozenInstanceError):
            offer.permits_open = True

    def test_simple_pdf_missing_or_invalid_conversion_blocks_without_fallback(self):
        with (
            patch.object(copies, "_trusted_converter", return_value=None),
            patch.object(copies, "run_limited_converter") as worker,
        ):
            missing = copies.assess_sanitized_pdf_copy(SIMPLE)
        worker.assert_not_called()
        self.assertEqual(missing.blocked_reason,
                         copies.SanitizationBlockReason.converterUnavailable)

        with (
            patch.object(copies, "_trusted_converter",
                         return_value=Path("/synthetic/trusted-converter")),
            patch.object(copies, "run_limited_converter",
                         return_value=subprocess.CompletedProcess([], 0, SIMPLE)),
        ):
            invalid = copies.assess_sanitized_pdf_copy(SIMPLE)
        self.assertEqual(invalid.blocked_reason,
                         copies.SanitizationBlockReason.outputUnverified)
        for blocked in (missing, invalid):
            self.assertEqual(blocked.action, "block")
            self.assertIsNone(blocked.offer)
            self.assertFalse(blocked.permits_open)
            self.assertFalse(blocked.allow_fallback)
            self.assertFalse(blocked.allow_clean_cache)
            self.assertTrue(blocked.preserve_quarantine)
            self.assertTrue(blocked.requires_separate_scan)

    def test_required_ci_runs_maximum_simple_pdf(self):
        command = "PYTHONPATH=. python3 tests/maximum/simple-pdf.py -v"
        for path in (".github/workflows/ci.yml",
                     ".github/workflows/consolidated-checks.yml"):
            with self.subTest(workflow=path):
                self.assertIn(command, (ROOT / path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
