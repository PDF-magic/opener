#!/usr/bin/env python3
"""Regression coverage for unsupported PDF feature response policy (opener-0254)."""

from dataclasses import FrozenInstanceError
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scan_results import ScanResultStatus
from unsupported_pdf_features import (
    ENCRYPTED_RESPONSE,
    ENCRYPTION_BLOCK_REASON,
    GENERIC_BLOCK_REASON,
    INCOMPLETE_RESPONSE,
    UNSUPPORTED_PDF_RESPONSES,
    UnsupportedPDFAction,
    UnsupportedPDFFeature,
    UnsupportedPDFResponse,
    response_for_unsupported_pdf_feature,
)

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("native_scan_gate", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class UnsupportedPDFFeaturePolicyTests(unittest.TestCase):
    def test_all_known_features_block_without_claiming_malware(self):
        self.assertEqual(set(UNSUPPORTED_PDF_RESPONSES), set(UnsupportedPDFFeature))
        for feature in UnsupportedPDFFeature:
            with self.subTest(feature=feature.value):
                response = response_for_unsupported_pdf_feature(feature)
                expected = (ScanResultStatus.encrypted if feature is
                            UnsupportedPDFFeature.UNINSPECTABLE_ENCRYPTION else
                            ScanResultStatus.incompleteScan)
                self.assertIs(response.action, UnsupportedPDFAction.BLOCK)
                self.assertIs(response.scan_status, expected)
                self.assertFalse(response.permits_open)
                self.assertFalse(response.scan_status.permits_open)
                self.assertTrue(response.preserve_quarantine)
                self.assertFalse(response.allow_clean_cache)
                self.assertFalse(response.allow_destination_handoff)
                self.assertFalse(response.allow_fallback)
                self.assertFalse(response.allow_override)
                self.assertNotIn("malware", response.reason.lower())
                self.assertNotIn("virus", response.reason.lower())

    def test_unrecognized_findings_also_block_without_echoing_private_data(self):
        for raw in ("unknown", "../../private/secret.pdf", "", None, 99, True, [],
                    {"feature": "unknown"}):
            with self.subTest(raw=repr(raw)):
                response = response_for_unsupported_pdf_feature(raw)
                self.assertIs(response, INCOMPLETE_RESPONSE)
                self.assertEqual(response.reason, GENERIC_BLOCK_REASON)
                self.assertFalse(response.permits_open)
        self.assertEqual(response_for_unsupported_pdf_feature(
            UnsupportedPDFFeature.UNINSPECTABLE_ENCRYPTION
        ).reason, ENCRYPTION_BLOCK_REASON)
        self.assertIs(response_for_unsupported_pdf_feature(
            UnsupportedPDFFeature.UNINSPECTABLE_ENCRYPTION
        ), ENCRYPTED_RESPONSE)

    def test_definitions_are_immutable_and_cannot_be_weakened(self):
        with self.assertRaises(FrozenInstanceError):
            INCOMPLETE_RESPONSE.allow_fallback = True
        with self.assertRaises(TypeError):
            UNSUPPORTED_PDF_RESPONSES[UnsupportedPDFFeature.UNSUPPORTED_FILTER] = (
                ENCRYPTED_RESPONSE
            )
        with self.assertRaises(ValueError):
            UnsupportedPDFResponse(
                action=UnsupportedPDFAction.BLOCK,
                scan_status=ScanResultStatus.clean,
                reason=GENERIC_BLOCK_REASON,
            )
        for relaxed in ("preserve_quarantine", "allow_clean_cache",
                        "allow_destination_handoff", "allow_fallback",
                        "allow_override"):
            kwargs = dict(action=UnsupportedPDFAction.BLOCK,
                          scan_status=ScanResultStatus.incompleteScan,
                          reason=GENERIC_BLOCK_REASON)
            kwargs[relaxed] = False if relaxed == "preserve_quarantine" else True
            with self.subTest(relaxed=relaxed), self.assertRaises(ValueError):
                UnsupportedPDFResponse(**kwargs)
        with self.assertRaises(ValueError):
            UnsupportedPDFResponse(
                action=UnsupportedPDFAction.BLOCK,
                scan_status=ScanResultStatus.incompleteScan,
                reason="/private/secret.pdf: unsupported",
            )

    def test_existing_scan_gate_blocks_unscannable_evidence_before_handoff(self):
        with tempfile.TemporaryDirectory(prefix="unsupported-pdf-") as directory:
            root = Path(directory)
            pdf = root / "not-inspectable.pdf"
            pdf.write_bytes(b"%PDF-1.4\nFixture only")
            events = (
                subprocess.CompletedProcess([], 1,
                    "file: Heuristics.Encrypted.PDF FOUND\n", ""),
                subprocess.CompletedProcess([], 1,
                    "file: Heuristics.Limits.Exceeded.MaxScanSize FOUND\n", ""),
                subprocess.CompletedProcess([], 2, "", "unsupported filter"),
                subprocess.CompletedProcess([], 0,
                    "file: OK\nWARNING: unsupported PDF feature", ""),
            )
            for completed in events:
                with self.subTest(code=completed.returncode, output=completed.stdout):
                    cache_file = root / ("cache-" + str(events.index(completed)) + ".sqlite")
                    with patch.object(gate, "CACHE_DB", cache_file), \
                         patch.object(gate, "verify_launch_target"), \
                         patch.object(gate, "scan_engine_version", return_value=None), \
                         patch.object(gate.subprocess, "run", return_value=completed), \
                         patch.object(gate, "remove_quarantine") as remove, \
                         patch.object(gate, "launch_clean_file") as launch, \
                         patch.object(gate, "remember_clean") as remember:
                        with self.assertRaises(RuntimeError):
                            gate.scan_and_open(str(pdf), "/scanner")
                    remove.assert_not_called()
                    launch.assert_not_called()
                    remember.assert_not_called()

    def test_policy_remains_declarative_without_adding_a_pdf_parser_or_override(self):
        gate_source = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("unsupported_pdf_features", gate_source)
        self.assertIn("'--alert-exceeds-max=yes', '--alert-encrypted=yes'", gate_source)
        self.assertIn("if not decision.allowed:", gate_source)
        self.assertIn("remove_quarantine(path)", gate_source)
        self.assertIn("if not cached_clean(cache_id):", gate_source)
        profiles = (ROOT / "protection_profiles.py").read_text(encoding="utf-8")
        self.assertIn("selectable: bool = False", profiles)


if __name__ == "__main__":
    unittest.main()
