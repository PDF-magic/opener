#!/usr/bin/env python3
"""Fail-closed unsupported Maximum sanitization cases (opener-0323)."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject, BooleanObject, DictionaryObject, NameObject,
    NumberObject, StreamObject, TextStringObject,
)

import maximum_sanitized_copy as sanitizer


def source_pdf(*, pages=1):
    writer = PdfWriter()
    for i in range(pages):
        writer.add_blank_page(width=180 + i, height=250)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def unsupported_pdf(feature):
    writer = PdfWriter()
    page = writer.add_blank_page(width=180, height=250)
    root = writer._root_object
    if feature == "xfa":
        root[NameObject("/AcroForm")] = writer._add_object(DictionaryObject({
            NameObject("/XFA"): TextStringObject("untrusted-dynamic-form"),
        }))
    elif feature == "signed":
        root[NameObject("/AcroForm")] = writer._add_object(DictionaryObject({
            NameObject("/SigFlags"): NumberObject(1),
        }))
    elif feature == "portfolio":
        root[NameObject("/Collection")] = writer._add_object(DictionaryObject())
    elif feature == "layers":
        root[NameObject("/OCProperties")] = writer._add_object(DictionaryObject())
    elif feature == "dynamic":
        root[NameObject("/NeedsRendering")] = BooleanObject(True)
    elif feature == "permissions":
        root[NameObject("/Perms")] = writer._add_object(DictionaryObject())
    elif feature in ("3d", "rich-media", "movie", "screen", "sound"):
        subtype = {
            "3d": "/3D", "rich-media": "/RichMedia",
            "movie": "/Movie", "screen": "/Screen", "sound": "/Sound",
        }[feature]
        annotation = writer._add_object(DictionaryObject({
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject(subtype),
        }))
        page[NameObject("/Annots")] = ArrayObject([annotation])
    elif feature in ("unknown-filter", "crypt-filter"):
        raw = StreamObject()
        raw._data = b"q Q\n"
        raw[NameObject("/Filter")] = NameObject(
            "/UnknownEncoding" if feature == "unknown-filter" else "/Crypt"
        )
        page[NameObject("/Contents")] = writer._add_object(raw)
    elif feature == "unknown-image-filter":
        raw = StreamObject()
        raw._data = b"fake image bytes"
        raw[NameObject("/Subtype")] = NameObject("/Image")
        raw[NameObject("/Filter")] = NameObject("/ImpossibleImageCodec")
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/XObject"): DictionaryObject({
                NameObject("/Im0"): writer._add_object(raw),
            }),
        })
    else:
        raise ValueError("Unknown synthetic feature")
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def encrypted_pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=180, height=250)
    writer.encrypt("private-password")
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


class UnsupportedSanitizationTests(unittest.TestCase):
    def assertBlocked(self, result, reason):
        self.assertIsNone(result.offer)
        self.assertEqual(result.blocked_reason, reason)
        self.assertEqual(result.action, "block")
        self.assertFalse(result.permits_open)
        self.assertFalse(result.allow_fallback)
        self.assertFalse(result.allow_clean_cache)
        self.assertTrue(result.preserve_quarantine)
        self.assertTrue(result.requires_separate_scan)
        document = result.to_dict()
        self.assertEqual(document, {
            "action": "block", "reason": reason.value,
            "offerAvailable": False, "pageCount": None,
            "permitsOpen": False, "allowFallback": False,
            "allowCleanCache": False, "preserveQuarantine": True,
            "requiresSeparateScan": True,
        })

    def test_explicitly_blocks_unsupported_source_features_before_conversion(self):
        for feature in (
            "xfa", "signed", "portfolio", "layers", "dynamic",
            "permissions", "3d", "rich-media", "movie", "screen", "sound",
            "unknown-filter", "crypt-filter", "unknown-image-filter",
        ):
            with self.subTest(feature=feature):
                pdf = unsupported_pdf(feature)
                with patch.object(sanitizer, "_trusted_converter",
                                  return_value=Path("/usr/bin/true")), \
                     patch.object(sanitizer.subprocess, "run") as run:
                    decision = sanitizer.assess_sanitized_pdf_copy(pdf)
                    self.assertBlocked(
                        decision, sanitizer.SanitizationBlockReason.unsupportedFeature)
                    self.assertIsNone(sanitizer.offer_sanitized_pdf_copy(pdf))
                    run.assert_not_called()

    def test_invalid_input_and_unreadable_sources_block_without_execution(self):
        for data in (None, True, "text", b"", bytearray(source_pdf()),
                     b"%PDF-1.7\nbroken", b"%PDF-" + b"x" * sanitizer.MAX_SOURCE_BYTES,
                     b"not a pdf"):
            with self.subTest(item=type(data).__name__), \
                 patch.object(sanitizer, "_trusted_converter",
                              return_value=Path("/usr/bin/true")), \
                 patch.object(sanitizer.subprocess, "run") as run:
                decision = sanitizer.assess_sanitized_pdf_copy(data)
                self.assertEqual(decision.action, "block")
                self.assertIsNone(decision.offer)
                run.assert_not_called()

    def test_encrypted_and_too_many_pages_do_not_attempt_conversion(self):
        for data, reason in (
            (encrypted_pdf(), sanitizer.SanitizationBlockReason.encryptedSource),
            (source_pdf(pages=sanitizer.MAX_PAGES + 1),
             sanitizer.SanitizationBlockReason.unsupportedPages),
        ):
            with self.subTest(reason=reason), \
                 patch.object(sanitizer, "_trusted_converter",
                              return_value=Path("/usr/bin/true")), \
                 patch.object(sanitizer.subprocess, "run") as run:
                self.assertBlocked(sanitizer.assess_sanitized_pdf_copy(data), reason)
                run.assert_not_called()

    def test_missing_or_failing_converter_is_an_explicit_block(self):
        pdf = source_pdf()
        with patch.object(sanitizer, "_trusted_converter", return_value=None):
            self.assertBlocked(sanitizer.assess_sanitized_pdf_copy(pdf),
                               sanitizer.SanitizationBlockReason.converterUnavailable)
        with patch.object(sanitizer, "_trusted_converter",
                          side_effect=OSError("/private/secret.pdf")):
            self.assertBlocked(sanitizer.assess_sanitized_pdf_copy(pdf),
                               sanitizer.SanitizationBlockReason.converterUnavailable)

    def test_nonzero_truncated_identical_and_oversized_results_block(self):
        pdf = source_pdf()
        outputs = (
            subprocess.CompletedProcess([], 2, b"%PDF-different"),
            subprocess.CompletedProcess([], 0, b""),
            subprocess.CompletedProcess([], 0, pdf),
            subprocess.CompletedProcess([], 0, b"X" * (sanitizer.MAX_OUTPUT_BYTES + 1)),
        )
        with patch.object(sanitizer, "_trusted_converter",
                          return_value=Path("/usr/bin/true")):
            for completed in outputs:
                with self.subTest(code=completed.returncode, size=len(completed.stdout)), \
                     patch.object(sanitizer.subprocess, "run", return_value=completed):
                    expected = (sanitizer.SanitizationBlockReason.conversionFailed
                                if completed.returncode != 0
                                else sanitizer.SanitizationBlockReason.outputUnverified)
                    self.assertBlocked(sanitizer.assess_sanitized_pdf_copy(pdf), expected)
            for error in (OSError("/private/secret.pdf"),
                          subprocess.TimeoutExpired("secret.pdf", 2)):
                with self.subTest(type=type(error).__name__), \
                     patch.object(sanitizer.subprocess, "run", side_effect=error):
                    self.assertBlocked(sanitizer.assess_sanitized_pdf_copy(pdf),
                                       sanitizer.SanitizationBlockReason.conversionFailed)

    def test_unverified_rebuild_cannot_offer_or_fall_back_to_original(self):
        original = source_pdf()
        converted = source_pdf(pages=2)
        with patch.object(sanitizer, "_trusted_converter",
                          return_value=Path("/usr/bin/true")), \
             patch.object(sanitizer.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, converted)):
            for rebuilt in (None, "not bytes", original, b""):
                with self.subTest(rebuilt=type(rebuilt).__name__), \
                     patch.object(sanitizer, "remove_active_pdf_functionality",
                                  return_value=rebuilt):
                    decision = sanitizer.assess_sanitized_pdf_copy(original)
                    self.assertBlocked(decision, sanitizer.SanitizationBlockReason.outputUnverified)
                    self.assertIsNone(sanitizer.offer_sanitized_pdf_copy(original))
            with patch.object(sanitizer, "remove_active_pdf_functionality",
                              return_value=converted), \
                 patch.object(sanitizer, "_passive_pages", return_value=False):
                self.assertBlocked(sanitizer.assess_sanitized_pdf_copy(original),
                                   sanitizer.SanitizationBlockReason.outputUnverified)
            with patch.object(sanitizer, "remove_active_pdf_functionality",
                              side_effect=RuntimeError("raw document details")):
                self.assertBlocked(sanitizer.assess_sanitized_pdf_copy(original),
                                   sanitizer.SanitizationBlockReason.outputUnverified)

    def test_verified_rebuild_only_offers_a_separately_scannable_copy(self):
        original = source_pdf()
        converted = source_pdf(pages=2)
        cleaned = source_pdf()
        with patch.object(sanitizer, "_trusted_converter",
                          return_value=Path("/usr/bin/true")), \
             patch.object(sanitizer.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, converted)), \
             patch.object(sanitizer, "remove_active_pdf_functionality",
                          return_value=cleaned), \
             patch.object(sanitizer, "_passive_pages", return_value=True):
            # The fixture's only role is to verify the typed post-rebuild
            # admission contract; real raster decoding is covered separately.
            decision = sanitizer.assess_sanitized_pdf_copy(original)
        self.assertEqual(decision.action, "block" if cleaned == original
                         else "offerForSeparateScan")
        # Identity with the source must never be offered.
        self.assertIsNone(decision.offer)
        self.assertFalse(decision.permits_open)

    def test_verified_distinct_rebuild_has_no_clean_or_open_verdict(self):
        original = source_pdf()
        converted = source_pdf(pages=2)
        cleaned = source_pdf(pages=3)
        with patch.object(sanitizer, "_trusted_converter",
                          return_value=Path("/usr/bin/true")), \
             patch.object(sanitizer.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, converted)), \
             patch.object(sanitizer, "remove_active_pdf_functionality",
                          return_value=cleaned), \
             patch.object(sanitizer, "_passive_pages", return_value=True), \
             patch.object(sanitizer, "verify_sanitized_pdf_structure",
                          return_value=__import__("maximum_sanitized_structure").SanitizedPDFStructure(1, 5)):
            decision = sanitizer.assess_sanitized_pdf_copy(original)
        self.assertEqual(decision.action, "offerForSeparateScan")
        self.assertIsNone(decision.blocked_reason)
        self.assertIsInstance(decision.offer, sanitizer.SanitizedCopyOffer)
        self.assertEqual(decision.offer.pdf_bytes, cleaned)
        self.assertFalse(decision.permits_open)
        self.assertFalse(decision.allow_clean_cache)
        self.assertFalse(decision.allow_fallback)
        self.assertEqual(decision.to_dict()["pageCount"], 1)
        self.assertIs(decision.to_dict()["reason"], None)

    def test_decision_is_immutable_and_rejects_false_success_records(self):
        blocked = sanitizer.assess_sanitized_pdf_copy(b"bad")
        with self.assertRaises(FrozenInstanceError):
            blocked.blocked_reason = None
        for offer, reason in (
            (None, None),
            (None, "unsupportedFeature"),
            ("raw pdf bytes", None),
            (sanitizer.SanitizedCopyOffer(b"%PDF-test", 1),
             sanitizer.SanitizationBlockReason.conversionFailed),
        ):
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                sanitizer.SanitizationDecision(offer, reason)

    def test_block_decisions_do_not_echo_pdf_content_or_private_path(self):
        pdf = unsupported_pdf("xfa")
        with patch.object(sanitizer, "_trusted_converter",
                          return_value=Path("/usr/bin/true")):
            decision = sanitizer.assess_sanitized_pdf_copy(pdf)
        value = str(decision.to_dict())
        for secret in ("untrusted-dynamic-form", "/private/", "secret.pdf",
                       "raw document details", "malware found"):
            self.assertNotIn(secret, value)
        self.assertNotIn("clean", decision.action)

    def test_benign_javascript_and_attachments_are_not_blanket_rejected(self):
        # Active input is allowed to reach the *separate* raster converter;
        # the output must still pass re-rendering and passive verification.
        writer = PdfWriter()
        writer.add_blank_page(width=180, height=250)
        writer.add_js("app.alert('not to run')")
        writer.add_attachment("private.txt", b"secret")
        out = BytesIO()
        writer.write(out)
        with patch.object(sanitizer, "_trusted_converter",
                          return_value=Path("/usr/bin/true")), \
             patch.object(sanitizer.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 2, b"")) as run:
            decision = sanitizer.assess_sanitized_pdf_copy(out.getvalue())
        run.assert_called_once()
        self.assertBlocked(decision, sanitizer.SanitizationBlockReason.conversionFailed)

    def test_existing_scanner_and_user_options_are_unchanged(self):
        root = Path(__file__).resolve().parent
        scan = (root / "scan-and-open.py").read_text()
        self.assertNotIn("maximum_sanitized_copy", scan)
        self.assertNotIn("assess_sanitized_pdf_copy", scan)
        self.assertIn("if not cached_clean(cache_id):", scan)
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)


if __name__ == "__main__":
    unittest.main()
