#!/usr/bin/env python3
"""opener-0342: no supported malware scan exceptions or user bypasses."""

from dataclasses import FrozenInstanceError, replace
import importlib.util
import inspect
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from effective_protection_policy import (
    ACTIVE_PROFILE_ID,
    resolve_effective_policy,
)
from protection_exception_policy import (
    EXCEPTION_SUPPORT_DECISION,
    ExceptionDisposition,
    ProtectionExceptionDecision,
    ProtectionExceptionNotSupported,
    request_protection_exception,
)
from protection_policy_definitions import BASELINE_CONTROLS, PROTECTION_POLICIES
from protection_profiles import PROTECTION_PROFILES

ROOT = Path(__file__).resolve().parents[2]
VIEW = (ROOT / "PDFMagicOpenerApp/ProtectionSettingsView.swift").read_text()
CI = (ROOT / ".github/workflows/ci.yml").read_text()


class ProtectionExceptionDecisionTests(unittest.TestCase):
    def test_support_decision_is_unconditionally_no_for_every_profile(self):
        decision = EXCEPTION_SUPPORT_DECISION
        self.assertFalse(decision.supported)
        self.assertIs(decision.disposition, ExceptionDisposition.UNSUPPORTED)
        self.assertEqual(decision.as_document(), {
            "supported": False,
            "disposition": "unsupported",
            "scope": "all_files_sources_destinations_and_protection_levels",
        })
        for profile, policy in PROTECTION_POLICIES.items():
            with self.subTest(profile=profile.value):
                self.assertFalse(policy.selectable)
                self.assertFalse(PROTECTION_PROFILES[profile].selectable)
                self.assertEqual(
                    {control for control in BASELINE_CONTROLS}.issubset(
                        {req.control for req in policy.requirements}
                    ), True,
                )
        active = resolve_effective_policy()
        self.assertEqual(active.profile_id, ACTIVE_PROFILE_ID)
        self.assertEqual(active.required_checks, frozenset(BASELINE_CONTROLS))

    def test_no_mutation_or_opt_in_can_change_exception_support(self):
        with self.assertRaises(FrozenInstanceError):
            EXCEPTION_SUPPORT_DECISION.supported = True
        for change in (
            {"supported": True},
            {"supported": 1},
            {"supported": "true"},
            {"disposition": "allow"},
            {"disposition": None},
        ):
            with self.subTest(change=change), self.assertRaises(
                ProtectionExceptionNotSupported
            ):
                replace(EXCEPTION_SUPPORT_DECISION, **change)
        detached = EXCEPTION_SUPPORT_DECISION.as_document()
        detached["supported"] = True
        self.assertFalse(EXCEPTION_SUPPORT_DECISION.supported)

    def test_any_exception_request_fails_without_reading_its_content(self):
        class PoisonRequest:
            def __getattribute__(self, _name):
                raise AssertionError("Exception data must never be inspected")
            def __str__(self):
                raise AssertionError("Exception data must never be logged")
        for attempt in (
            None, "report.pdf", "/Downloads", {"path": "report.pdf"},
            {"source": "untrusted"}, {"app": "com.apple.Safari"},
            {"bypass": True}, PoisonRequest(),
        ):
            with self.subTest(type=type(attempt).__name__):
                with self.assertRaises(ProtectionExceptionNotSupported) as caught:
                    request_protection_exception(attempt)
                self.assertEqual(
                    str(caught.exception),
                    "Protection exceptions are not supported; mandatory scanning remains required.",
                )

    def test_user_requested_exemption_cannot_override_infected_scan(self):
        spec = importlib.util.spec_from_file_location(
            "scanner_for_exception_test", ROOT / "scan-and-open.py")
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.pdf"
            path.write_bytes(b"%PDF-1.4\nuntrusted")
            virus = subprocess.CompletedProcess(
                [], 1, f"{path}: Eicar-Test-Signature FOUND\n", "")
            with patch.object(module, "CACHE_DB", Path(directory) / "clean.sqlite3"), \
                 patch.object(module, "SCAN_REQUEST_DB", Path(directory) / "requests.sqlite3"), \
                 patch.object(module, "verify_launch_target"), \
                 patch.object(module.subprocess, "check_output", side_effect=FileNotFoundError), \
                 patch.object(module.subprocess, "run", return_value=virus) as scan, \
                 patch.object(module, "remove_quarantine") as unquarantine, \
                 patch.object(module, "launch_clean_file") as launch:
                # Protection level is descriptive request metadata, never
                # a bypass selector; pretend the caller asks for an exception.
                with self.assertRaises(RuntimeError) as caught:
                    module.scan_and_open(str(path), "/scanner",
                                         protection_level="skip-malware-check")
                self.assertIn("opening was stopped", str(caught.exception))
                self.assertEqual(caught.exception.scan_result.detection_names,
                                 ("Eicar-Test-Signature",))
                self.assertEqual(scan.call_count, 1)
                unquarantine.assert_not_called()
                launch.assert_not_called()

    def test_no_exception_parameters_or_scanner_exception_registry_exist(self):
        scanner = (ROOT / "scan-and-open.py").read_text()
        for entry in ("scan_and_open", "scan_and_open_generated_copy"):
            self.assertIn(f"def {entry}(", scanner)
        for forbidden in (
            "skip_scan=", "allowlisted=", "ignore_malware=",
            "exception_patterns=", "trusted_source_allowlist",
            "PROTECTION_EXCEPTION_ALLOWLIST",
            "EXCEPTION_SUPPORT_DECISION",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("decision = decide_opening(detection)", scanner)
        self.assertIn("verify_file_integrity(path, before, identity)", scanner)
        self.assertIn("force_rescan=True, expected_fingerprint=expected", scanner)
        self.assertIn("--alert-encrypted=yes", scanner)

    def test_ui_explains_unsupported_exceptions_without_bypass_controls(self):
        for fragment in (
            'GroupBox("Protection exceptions")',
            "Protection exceptions are not supported.",
            "No file, folder, download source or application can be exempted",
            "A verified clean-scan cache hit or an approved alternative PDF viewer is not an exception",
            "There is no protection allowlist or bypass control.",
            'accessibilityIdentifier("protectionExceptionsUnsupported")',
            "Active protection: Built-in ClamAV",
        ):
            self.assertIn(fragment, VIEW)
        section = VIEW.split('GroupBox("Protection exceptions")', 1)[1].split(
            'GroupBox("Malware scanning")', 1)[0]
        for forbidden in ("Button(", "Toggle(", "Picker(", "@AppStorage", "UserDefaults",
                          "NSWorkspace", "Process(", "onTapGesture", "saveExplicitChoice"):
            self.assertNotIn(forbidden, section)

    def test_ci_and_documented_policy(self):
        self.assertIn("python3 tests/protection/exceptions-decision.py -v", CI)
        self.assertIn("macos-build:", CI)
        document = (ROOT / "docs/protection/exceptions-decision.md").read_text()
        for phrase in ("Exceptions: unsupported", "cache", "fallback", "Built-in"):
            self.assertIn(phrase, document)


if __name__ == "__main__":
    unittest.main()
