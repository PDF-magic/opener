#!/usr/bin/env python3
"""opener-0265: same deterministic reference PDFs for all profile contracts.

Standard, Enhanced and Maximum are not executable today. Their shared corpus
must fail policy admission rather than falsely reporting simulated ClamAV
scans as executions of those profiles. The installed Built-in gate is tested
independently with deterministic, injected scanner outcomes on that SAME
corpus. These are integration-contract tests, not live antivirus benchmarks.
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
from protection_policy_definitions import (
    BASELINE_CONTROLS,
    ControlAvailability,
    FailureDisposition,
    PROTECTION_POLICIES,
)
from protection_profiles import ProtectionProfileID, PROTECTION_PROFILES
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("reference_scan_gate", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class SameReferencePDFCollectionTests(unittest.TestCase):
    def test_reference_collection_is_stable_unique_and_real_pdf_syntax(self):
        self.assertEqual(len(REFERENCE_PDFS), 6)
        self.assertEqual(len({sample.identifier for sample in REFERENCE_PDFS}), 6)
        self.assertEqual(len({sha256(sample.content).digest() for sample in REFERENCE_PDFS}), 6)
        self.assertEqual(
            {sample.simulated_scanner_outcome for sample in REFERENCE_PDFS},
            {"clean", "detected", "incomplete", "failed", "timeout"},
        )
        for sample in REFERENCE_PDFS:
            with self.subTest(pdf=sample.identifier):
                self.assertTrue(sample.content.startswith(b"%PDF-1.4\n"))
                self.assertTrue(sample.content.endswith(b"%%EOF\n"))
                self.assertIn(b"trailer\n", sample.content)
                self.assertIn(b"startxref\n", sample.content)
                offsets = sample.content.split(b"xref\n")[1].split(b"trailer\n")[0]
                lines = offsets.splitlines()
                self.assertEqual(lines[0], b"0 6")
                self.assertEqual(len(lines), 7)
                for index, row in enumerate(lines[2:], start=1):
                    offset = int(row[:10])
                    self.assertTrue(sample.content[offset:].startswith(
                        str(index).encode("ascii") + b" 0 obj\n"
                    ))
                startxref = int(sample.content.split(b"startxref\n")[1].splitlines()[0])
                self.assertEqual(sample.content[startxref:startxref + 5], b"xref\n")

    def test_every_planned_profile_uses_exactly_same_corpus_but_cannot_activate(self):
        expected_fingerprints = tuple(
            (sample.identifier, sha256(sample.content).hexdigest())
            for sample in REFERENCE_PDFS
        )
        tested = {}
        for profile in ProtectionProfileID:
            with self.subTest(profile=profile.value):
                policy = PROTECTION_POLICIES[profile]
                self.assertEqual(policy.profile_id, profile)
                self.assertFalse(policy.selectable)
                self.assertFalse(PROTECTION_PROFILES[profile].selectable)
                self.assertIs(policy.failure_disposition, FailureDisposition.DENY)
                self.assertEqual(
                    {req.control for req in policy.requirements
                     if req.availability is ControlAvailability.CURRENT},
                    set(BASELINE_CONTROLS),
                )
                tested[profile] = []
                for sample in REFERENCE_PDFS:
                    with self.subTest(profile=profile.value, pdf=sample.identifier):
                        # Try to admit this EXACT PDF under its named policy.
                        # Unsupported selections must be refused before calling a scan.
                        with patch.object(gate, "scan_and_open") as scan:
                            with self.assertRaises(UnsupportedEffectivePolicy):
                                resolve_effective_policy({
                                    SELECTED_PROFILE_KEY: profile.value
                                })
                            scan.assert_not_called()
                        tested[profile].append(
                            (sample.identifier, sha256(sample.content).hexdigest())
                        )
                self.assertEqual(tuple(tested[profile]), expected_fingerprints)
        self.assertEqual(set(tested), set(ProtectionProfileID))
        self.assertEqual(len(tested) * len(REFERENCE_PDFS), 18)

    def test_deployed_builtin_gate_handles_same_corpus_without_live_scanner(self):
        # The live Built-in gate is not a substitute for planned profile tests.
        self.assertEqual(resolve_effective_policy().profile_id, ACTIVE_PROFILE_ID)
        with tempfile.TemporaryDirectory(prefix="pdf-magic-reference-corpus-") as temp:
            directory = Path(temp)
            for sample in REFERENCE_PDFS:
                with self.subTest(pdf=sample.identifier):
                    source = directory / (sample.identifier + ".pdf")
                    source.write_bytes(sample.content)
                    initial_digest = sha256(source.read_bytes()).digest()
                    cache_file = directory / (sample.identifier + "-cache.sqlite3")
                    observed = []

                    def fake_scanner(command, timeout):
                        observed.append((tuple(command), timeout))
                        if sample.simulated_scanner_outcome == "timeout":
                            raise subprocess.TimeoutExpired(command, timeout)
                        if sample.simulated_scanner_outcome == "detected":
                            return subprocess.CompletedProcess(
                                command, 1, "reference: Synthetic.Test.Verification FOUND", ""
                            )
                        if sample.simulated_scanner_outcome == "incomplete":
                            return subprocess.CompletedProcess(
                                command, 0, "reference: OK", "WARNING: incomplete check"
                            )
                        if sample.simulated_scanner_outcome == "failed":
                            return subprocess.CompletedProcess(command, 2, "", "scanner failed")
                        return subprocess.CompletedProcess(command, 0, "reference: OK", "")

                    with ExitStack() as stack:
                        stack.enter_context(patch.object(gate, "CACHE_DB", cache_file))
                        stack.enter_context(patch.object(
                            gate, "SCAN_REQUEST_DB", directory / (sample.identifier + "-audit.sqlite3")
                        ))
                        stack.enter_context(patch.object(
                            gate, "intended_destination", return_value="com.brave.Browser"
                        ))
                        stack.enter_context(patch.object(
                            gate, "pdf_fallback_application", return_value=None
                        ))
                        stack.enter_context(patch.object(gate, "verify_local_file_available"))
                        stack.enter_context(patch.object(gate, "verify_launch_target"))
                        stack.enter_context(patch.object(gate, "record_scan_destination"))
                        stack.enter_context(patch.object(
                            gate, "read_signature_database_version", return_value=None
                        ))
                        stack.enter_context(patch.object(
                            gate, "scan_engine_version", return_value="test-only"
                        ))
                        stack.enter_context(patch.object(
                            gate, "run_scan_command", side_effect=fake_scanner
                        ))
                        quarantine = stack.enter_context(patch.object(gate, "remove_quarantine"))
                        launcher = stack.enter_context(patch.object(gate, "launch_clean_file"))
                        if sample.simulated_scanner_outcome == "clean":
                            result = gate.scan_and_open(str(source), "/mock-scanner")
                            self.assertEqual(result.status, "clean")
                            quarantine.assert_called_once_with(source)
                            launcher.assert_called_once()
                        else:
                            with self.assertRaises(RuntimeError) as blocked:
                                gate.scan_and_open(str(source), "/mock-scanner")
                            self.assertIn("opening was stopped", str(blocked.exception))
                            self.assertNotIn(str(source), str(blocked.exception))
                            quarantine.assert_not_called()
                            launcher.assert_not_called()
                            self.assertFalse(gate.cached_clean(gate.cache_key(
                                gate.fingerprint(source), True
                            )))
                    self.assertEqual(len(observed), 1, "Every fixture requires a scanner verdict")
                    self.assertEqual(observed[0][1], gate.PDF_SCAN_TIMEOUT)
                    self.assertEqual(observed[0][0][-1], str(source))
                    self.assertEqual(sha256(source.read_bytes()).digest(), initial_digest)

    def test_ci_registers_reference_suite_without_claiming_profiles_are_live(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/run-test.py tests/general/reference-pdf-profiles.py -v", workflow)
        self.assertNotIn("reference_pdf_collection", (ROOT / "scan-and-open.py").read_text(encoding="utf-8"))
        self.assertIn("not executable", __doc__)
        self.assertEqual(len(tuple(ProtectionProfileID)), 3)


if __name__ == "__main__":
    unittest.main()
