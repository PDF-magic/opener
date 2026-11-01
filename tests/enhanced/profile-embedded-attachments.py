#!/usr/bin/env python3
"""opener-1015: Enhanced admission and attachment inspection regression tests.

Enhanced is not executable yet. These tests deliberately keep profile
admission separate from its optional embedded-file inspection building block.
They use synthetic, harmless attachments and simulated ClamAV responses.
"""

from io import BytesIO
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter

import enhanced_embedded_files as inspector
from effective_protection_policy import (
    SELECTED_PROFILE_KEY,
    UnsupportedEffectivePolicy,
    resolve_effective_policy,
)
from protection_policy_definitions import (
    BASELINE_CONTROLS,
    FailureDisposition,
    PROTECTION_POLICIES,
)
from protection_profiles import ProtectionProfileID


ATTACHMENTS = (
    ("notes.txt", b"Harmless PDF attachment notes"),
    ("diagram.dat", b"Harmless attachment data"),
)


def attachment_pdf():
    """Build an actual PDF with two embedded file streams, not a fake header."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    for filename, payload in ATTACHMENTS:
        writer.add_attachment(filename, payload)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class EnhancedEmbeddedAttachmentProfileTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="enhanced-attachment-profile-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.pdf_path = root / "attachments.pdf"
        self.pdf_bytes = attachment_pdf()
        self.pdf_path.write_bytes(self.pdf_bytes)
        self.signature_database = root / "signatures"
        self.signature_database.mkdir()

        # Confirm this scenario genuinely contains embedded attachments.
        reader = PdfReader(BytesIO(self.pdf_bytes), strict=True)
        self.assertEqual(len(reader.pages), 1)
        self.assertEqual(
            set(reader.attachments),
            {filename for filename, _ in ATTACHMENTS},
        )
        for filename, payload in ATTACHMENTS:
            self.assertEqual(reader.attachments[filename][0], payload)

    def test_enhanced_denies_attachment_pdf_before_any_scan_or_handoff(self):
        profile = PROTECTION_POLICIES[ProtectionProfileID.ENHANCED]
        self.assertFalse(profile.selectable)
        self.assertIs(profile.failure_disposition, FailureDisposition.DENY)
        self.assertTrue(
            BASELINE_CONTROLS.issubset(
                {requirement.control for requirement in profile.requirements}
            )
        )

        preferences = {
            SELECTED_PROFILE_KEY: ProtectionProfileID.ENHANCED.value,
            "customBrowser": "com.example.SelectedBrowser",
        }
        original_preferences = preferences.copy()
        with patch.object(inspector.subprocess, "run") as scanner:
            with self.assertRaises(UnsupportedEffectivePolicy):
                resolve_effective_policy(preferences)
            scanner.assert_not_called()
        self.assertEqual(preferences, original_preferences)
        self.assertEqual(self.pdf_path.read_bytes(), self.pdf_bytes)

    def test_attachment_stage_scans_each_real_payload_without_approving_pdf(self):
        clean_reply = subprocess.CompletedProcess([], 0, b"stream: OK\n", b"")
        with patch.object(inspector.subprocess, "run", return_value=clean_reply) as scan:
            result = inspector.inspect_embedded_files(
                self.pdf_path, "/mock/clamscan", self.signature_database
            )

        self.assertEqual(result.inspected_count, len(ATTACHMENTS))
        self.assertEqual(result.inspected_bytes, sum(len(data) for _, data in ATTACHMENTS))
        self.assertIs(result.pdf_is_clean, False)
        self.assertEqual(
            [call.kwargs["input"] for call in scan.call_args_list],
            [payload for _, payload in ATTACHMENTS],
        )
        for call in scan.call_args_list:
            self.assertIn("--stdin", call.args[0])
            self.assertIn("--alert-encrypted=yes", call.args[0])
            self.assertTrue(call.kwargs["capture_output"])
        self.assertEqual(self.pdf_path.read_bytes(), self.pdf_bytes)

        # A clean attachment-only stage never enables the planned Enhanced tier.
        with self.assertRaises(UnsupportedEffectivePolicy):
            resolve_effective_policy({SELECTED_PROFILE_KEY: "enhanced"})

    def test_embedded_detection_or_incomplete_scan_blocks_attachment_stage(self):
        clean = subprocess.CompletedProcess([], 0, b"stream: OK\n", b"")
        rejected = (
            subprocess.CompletedProcess([], 1, b"stream: Synthetic.Test FOUND\n", b""),
            subprocess.CompletedProcess([], 0, b"stream: OK\n", b"WARNING"),
            subprocess.CompletedProcess([], 0, b"", b""),
            subprocess.TimeoutExpired(["/mock/clamscan"], 120),
        )
        for failure in rejected:
            with self.subTest(failure=type(failure).__name__, detail=str(failure)[:35]):
                replies = [clean, failure]
                with patch.object(inspector.subprocess, "run", side_effect=replies) as scan:
                    with self.assertRaises(inspector.EmbeddedFileInspectionError) as error:
                        inspector.inspect_embedded_files(
                            self.pdf_path, "/mock/clamscan", self.signature_database
                        )
                self.assertEqual(str(error.exception), inspector.BLOCK_MESSAGE)
                self.assertEqual(scan.call_count, 2)
                self.assertNotIn("notes.txt", str(error.exception))
                self.assertNotIn("diagram.dat", str(error.exception))
                self.assertEqual(self.pdf_path.read_bytes(), self.pdf_bytes)

    def test_installed_builtin_policy_remains_independent_of_enhanced(self):
        active = resolve_effective_policy({"customBrowser": "com.example.SelectedBrowser"})
        self.assertEqual(active.profile_id, "built-in")
        self.assertEqual(active.required_checks, frozenset(BASELINE_CONTROLS))
        self.assertIs(active.failure_disposition, FailureDisposition.DENY)
        self.assertFalse(active.optional_checks)


if __name__ == "__main__":
    unittest.main()
