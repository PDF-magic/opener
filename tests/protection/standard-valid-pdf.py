#!/usr/bin/env python3
"""opener-1010: exercise a valid PDF against Standard's existing safety floor.

Standard remains a non-selectable policy definition. A controlled ClamAV
response exercises the deployed Built-in gate; this test never activates an
unimplemented profile, invokes a real scanner, or launches a real PDF viewer.
"""

from contextlib import ExitStack
from hashlib import sha256
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pypdf import PdfReader

from effective_protection_policy import (
    ACTIVE_PROFILE_ID,
    SELECTED_PROFILE_KEY,
    UnsupportedEffectivePolicy,
    resolve_effective_policy,
)
from protection_policy_definitions import (
    BASELINE_CONTROLS,
    ControlAvailability,
    FailureDisposition,
    protection_policy_definition,
)
from protection_profiles import ProtectionProfileID, protection_profile_definition
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    "standard_valid_pdf_scanner", ROOT / "scan-and-open.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
CLEAN_PDF = next(sample for sample in REFERENCE_PDFS
                 if sample.identifier == "clean-basic")


class StandardValidPDFTests(unittest.TestCase):
    def test_standard_contract_with_real_valid_pdf_bytes(self):
        # Check more than a PDF header: the existing harmless fixture must
        # have a parseable page tree and readable page content.
        reader = PdfReader(io.BytesIO(CLEAN_PDF.content), strict=True)
        self.assertEqual(len(reader.pages), 1)
        self.assertEqual(reader.pages[0].extract_text().strip(), "Clean baseline")

        standard = protection_profile_definition(ProtectionProfileID.STANDARD)
        policy = protection_policy_definition(ProtectionProfileID.STANDARD)
        active = resolve_effective_policy()
        self.assertEqual(standard.display_name, "Standard")
        self.assertFalse(standard.selectable)
        self.assertFalse(policy.selectable)
        self.assertEqual(
            {requirement.control for requirement in policy.required_checks},
            set(BASELINE_CONTROLS),
        )
        self.assertTrue(all(
            requirement.availability is ControlAvailability.CURRENT
            for requirement in policy.required_checks
        ))
        self.assertIs(policy.failure_disposition, FailureDisposition.DENY)
        self.assertEqual(active.profile_id, ACTIVE_PROFILE_ID)
        self.assertEqual(active.required_checks, frozenset(BASELINE_CONTROLS))

        # A saved planned Standard selection must not silently become
        # authorization to scan/open under another policy.
        with patch.object(gate, "scan_and_open") as scan:
            with self.assertRaises(UnsupportedEffectivePolicy):
                resolve_effective_policy({SELECTED_PROFILE_KEY: "standard"})
            scan.assert_not_called()

    def test_valid_pdf_clean_scan_precedes_each_builtin_handoff(self):
        with tempfile.TemporaryDirectory(prefix="standard-valid-pdf-") as temp:
            directory = Path(temp)
            pdf = directory / "valid-standard-reference.pdf"
            pdf.write_bytes(CLEAN_PDF.content)
            digest_before = sha256(pdf.read_bytes()).digest()
            events = []

            def simulated_clamav(command, timeout):
                events.append("scan")
                self.assertEqual(command[-2:], ["--", str(pdf)])
                self.assertIn("--alert-encrypted=yes", command)
                self.assertIn("--alert-exceeds-max=yes", command)
                self.assertIn("--max-filesize=0", command)
                self.assertIn("--max-scansize=0", command)
                self.assertEqual(timeout, gate.PDF_SCAN_TIMEOUT)
                return subprocess.CompletedProcess(command, 0, str(pdf) + ": OK", "")

            def simulated_handoff(path, *, target_app=None):
                self.assertEqual(path, pdf)
                self.assertEqual(target_app, "com.brave.Browser")
                events.append("handoff")

            with ExitStack() as stack:
                stack.enter_context(patch.object(
                    gate, "CACHE_DB", directory / "clean-cache.sqlite3"))
                stack.enter_context(patch.object(
                    gate, "SCAN_REQUEST_DB", directory / "audit.sqlite3"))
                stack.enter_context(patch.object(
                    gate, "intended_destination", return_value="com.brave.Browser"))
                stack.enter_context(patch.object(
                    gate, "pdf_fallback_application", return_value=None))
                stack.enter_context(patch.object(gate, "verify_local_file_available"))
                verify_target = stack.enter_context(
                    patch.object(gate, "verify_launch_target"))
                stack.enter_context(patch.object(gate, "record_scan_destination"))
                stack.enter_context(patch.object(gate, "record_opened_document_origin"))
                stack.enter_context(patch.object(
                    gate, "read_signature_database_version", return_value=None))
                stack.enter_context(patch.object(
                    gate, "scan_engine_version", return_value="ClamAV-test"))
                scan = stack.enter_context(
                    patch.object(gate, "run_scan_command", side_effect=simulated_clamav))
                quarantine = stack.enter_context(patch.object(
                    gate, "remove_quarantine"))
                launch = stack.enter_context(patch.object(
                    gate, "launch_clean_file", side_effect=simulated_handoff))

                first = gate.scan_and_open(str(pdf), "/mock-clamscan")
                second = gate.scan_and_open(str(pdf), "/mock-clamscan")

                self.assertEqual(first.status, "clean")
                self.assertFalse(first.from_cache)
                self.assertEqual(second.status, "clean")
                self.assertTrue(second.from_cache)
                scan.assert_called_once()
                self.assertEqual(events, ["scan", "handoff", "handoff"])
                self.assertEqual(verify_target.call_count, 2)
                self.assertEqual(quarantine.call_count, 2)
                self.assertEqual(launch.call_count, 2)

            self.assertEqual(sha256(pdf.read_bytes()).digest(), digest_before)

    def test_ci_executes_valid_pdf_standard_regression(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "PYTHONPATH=. python3 tests/protection/standard-valid-pdf.py -v",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
