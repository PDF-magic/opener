#!/usr/bin/env python3
"""opener-1025: regress profile changes between consecutive PDF scan requests.

Planned Standard/Enhanced/Maximum selections are preview metadata, NOT live
scanner policies. Use real, harmless PDF bytes and injected ClamAV verdicts;
never launch a viewer, change a real preference, or activate an unfinished tier.
"""

from contextlib import ExitStack
from hashlib import sha256
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from effective_protection_policy import (
    ACTIVE_PROFILE_ID,
    SELECTED_PROFILE_KEY,
    UnsupportedEffectivePolicy,
    resolve_effective_policy,
)
from protection_policy_definitions import BASELINE_CONTROLS, FailureDisposition
from protection_profiles import ProtectionProfileID, protection_profile_definition
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    "consecutive_profile_scanner", ROOT / "scan-and-open.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ConsecutiveProfileSwitchTests(unittest.TestCase):
    def test_preview_switches_cannot_bypass_scans_or_carry_over_verdicts(self):
        # Every request has different valid bytes, so a fresh scanner verdict
        # is required. The third verdict is infected; a subsequent change back
        # to Standard must still invoke ClamAV before a clean handoff.
        cases = (
            ("standard", REFERENCE_PDFS[0], False),
            ("maximum", REFERENCE_PDFS[1], False),
            ("enhanced", REFERENCE_PDFS[2], True),
            ("standard", REFERENCE_PDFS[3], False),
        )
        preferences = {
            SELECTED_PROFILE_KEY: ACTIVE_PROFILE_ID,
            "preferredProtectionLevel": "standard",
            "customPDFBrowser": "preserve-user-choice",
            "showScanProgress": False,
        }
        self.assertEqual(gate.ACTIVE_SCAN_POLICY.snapshot(), gate.DEFAULT_SCAN_POLICY)
        with tempfile.TemporaryDirectory(prefix="profile-switch-regression-") as temp:
            directory = Path(temp)
            paths = []
            digests = []
            for index, (_, sample, _) in enumerate(cases):
                path = directory / f"scan-{index}.pdf"
                path.write_bytes(sample.content)
                paths.append(path)
                digests.append(sha256(path.read_bytes()).digest())

            observed = []
            opens = []

            def simulated_clamav(command, timeout):
                path = Path(command[-1])
                observed.append(path)
                self.assertEqual(command[-2:], ["--", str(path)])
                self.assertEqual(timeout, gate.PDF_SCAN_TIMEOUT)
                for flag in (
                    "--alert-encrypted=yes", "--alert-exceeds-max=yes",
                    "--max-filesize=0", "--max-scansize=0", "--max-scantime=0",
                ):
                    self.assertIn(flag, command)
                self.assertIn("--database=" + str(gate.DATABASE), command)
                if path == paths[2]:
                    return subprocess.CompletedProcess(
                        command, 1, "fixture: Synthetic.Test FOUND", ""
                    )
                return subprocess.CompletedProcess(command, 0, "fixture: OK", "")

            def simulated_handoff(path, *, target_app=None):
                self.assertEqual(target_app, "com.example.viewer")
                opens.append(path)

            with ExitStack() as stack:
                stack.enter_context(patch.object(
                    gate, "CACHE_DB", directory / "clean-cache.sqlite3"
                ))
                stack.enter_context(patch.object(
                    gate, "SCAN_REQUEST_DB", directory / "requests.sqlite3"
                ))
                stack.enter_context(patch.object(
                    gate, "intended_destination", return_value="com.example.viewer"
                ))
                stack.enter_context(patch.object(
                    gate, "pdf_fallback_application", return_value=None
                ))
                stack.enter_context(patch.object(gate, "verify_local_file_available"))
                stack.enter_context(patch.object(gate, "verify_launch_target"))
                stack.enter_context(patch.object(gate, "record_scan_destination"))
                stack.enter_context(patch.object(gate, "record_opened_document_origin"))
                stack.enter_context(patch.object(
                    gate, "read_signature_database_version", return_value=None
                ))
                stack.enter_context(patch.object(
                    gate, "scan_engine_version", return_value="test-only"
                ))
                scanner = stack.enter_context(patch.object(
                    gate, "run_scan_command", side_effect=simulated_clamav
                ))
                quarantine = stack.enter_context(patch.object(gate, "remove_quarantine"))
                stack.enter_context(patch.object(
                    gate, "launch_clean_file", side_effect=simulated_handoff
                ))
                requests = stack.enter_context(patch.object(
                    gate.ScanRequest, "from_path", wraps=gate.ScanRequest.from_path
                ))

                for index, (preview, sample, blocked) in enumerate(cases):
                    with self.subTest(scan=index, preview=preview):
                        self.assertFalse(
                            protection_profile_definition(ProtectionProfileID(preview)).selectable
                        )
                        preferences["preferredProtectionLevel"] = preview
                        before = dict(preferences)
                        effective = resolve_effective_policy(preferences)
                        self.assertEqual(effective.profile_id, ACTIVE_PROFILE_ID)
                        self.assertEqual(effective.required_checks, frozenset(BASELINE_CONTROLS))
                        self.assertIs(effective.failure_disposition, FailureDisposition.DENY)
                        self.assertEqual(preferences, before)
                        self.assertEqual(gate.ACTIVE_SCAN_POLICY.snapshot(),
                                         gate.DEFAULT_SCAN_POLICY)

                        # The request metadata is not an active policy switch.
                        if blocked:
                            with self.assertRaisesRegex(RuntimeError, "Malware was detected"):
                                gate.scan_and_open(
                                    str(paths[index]), "/test-clamscan",
                                    protection_level=preview,
                                )
                        else:
                            result = gate.scan_and_open(
                                str(paths[index]), "/test-clamscan",
                                protection_level=preview,
                            )
                            self.assertEqual(result.status, "clean")
                            self.assertFalse(result.from_cache)
                            self.assertEqual(result.effective_policy_id, ACTIVE_PROFILE_ID)
                        self.assertEqual(observed, paths[:index + 1])
                        self.assertEqual(
                            opens, [paths[j] for j in range(index + 1) if j != 2]
                        )

                self.assertEqual(scanner.call_count, len(cases))
                self.assertEqual(quarantine.call_count, 3)
                self.assertEqual(
                    [call.kwargs["protection_level"] for call in requests.call_args_list],
                    [preview for preview, _, _ in cases],
                )
                self.assertEqual(
                    [call.args[0] for call in requests.call_args_list], paths
                )

            self.assertEqual(
                [sha256(path.read_bytes()).digest() for path in paths], digests
            )
            self.assertEqual(preferences["customPDFBrowser"], "preserve-user-choice")
            self.assertIs(preferences["showScanProgress"], False)

    def test_unsupported_active_switch_between_requests_fails_closed(self):
        preferences = {
            SELECTED_PROFILE_KEY: ACTIVE_PROFILE_ID,
            "preferredProtectionLevel": "standard",
            "customPDFBrowser": "unchanged",
        }
        built_in = resolve_effective_policy(preferences)
        for unsupported in ("maximum", "enhanced", "standard"):
            with self.subTest(next_selection=unsupported):
                # An attempted ACTIVE switch is different from a preview
                # change: it must be refused rather than downgraded silently.
                preferences[SELECTED_PROFILE_KEY] = unsupported
                previous = dict(preferences)
                with patch.object(gate, "scan_and_open") as scanner:
                    with self.assertRaises(UnsupportedEffectivePolicy):
                        resolve_effective_policy(preferences)
                    scanner.assert_not_called()
                self.assertEqual(preferences, previous)
                preferences[SELECTED_PROFILE_KEY] = ACTIVE_PROFILE_ID
                self.assertIs(resolve_effective_policy(preferences), built_in)
        self.assertEqual(preferences["customPDFBrowser"], "unchanged")

    def test_ci_runs_consecutive_switch_regression(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "PYTHONPATH=. python3 tests/protection/consecutive-profile-switches.py -v",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
