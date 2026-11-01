#!/usr/bin/env python3
"""opener-1012: EICAR fixture checks for Standard's mandatory ClamAV floor.

Standard is a defined but non-selectable profile. Exercise the deployed
Built-in scan gate shared by its required controls; do not pretend to run
Standard as a separately installed policy. The default test uses a scanner
double, while CI additionally runs the same gate with actual ClamAV.
"""

from contextlib import ExitStack
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from effective_protection_policy import (
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


ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("standard_fixture_scan", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

# Canonical, harmless 68-byte EICAR antivirus test fixture. Assemble it at
# runtime rather than committing a complete detection string as a repository
# file that host antivirus software could quarantine.
EICAR_BYTES = (
    b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$"
    b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!"
    b"$H+H*"
)


class StandardAntivirusFixtureTests(unittest.TestCase):
    def test_standard_requires_same_mandatory_gate_but_is_not_selectable(self):
        identifier = ProtectionProfileID.STANDARD
        descriptor = protection_profile_definition(identifier)
        policy = protection_policy_definition(identifier)
        self.assertFalse(descriptor.selectable)
        self.assertFalse(policy.selectable)
        self.assertIs(policy.failure_disposition, FailureDisposition.DENY)
        self.assertEqual(
            {item.control for item in policy.requirements
             if item.availability is ControlAvailability.CURRENT},
            set(BASELINE_CONTROLS),
        )
        self.assertEqual(
            {item.control.value for item in policy.requirements},
            descriptor.required_safety_checks,
        )
        with self.assertRaises(UnsupportedEffectivePolicy):
            resolve_effective_policy({SELECTED_PROFILE_KEY: identifier.value})
        self.assertEqual(resolve_effective_policy().profile_id, "built-in")

    def test_fixture_has_canonical_eicar_bytes(self):
        self.assertEqual(len(EICAR_BYTES), 68)
        self.assertTrue(EICAR_BYTES.startswith(b"X5O!P%@AP[4\\"))
        self.assertIn(b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!", EICAR_BYTES)
        self.assertTrue(EICAR_BYTES.endswith(b"$H+H*"))

    def exercise_mandatory_gate(self, real_scanner=None):
        with tempfile.TemporaryDirectory(prefix="opener-standard-eicar-") as temp:
            root = Path(temp).resolve()
            # This is the exact EICAR fixture named as a PDF scan request;
            # it is intentionally not represented as a well-formed PDF.
            selected = root / "eicar-test.pdf"
            selected.write_bytes(EICAR_BYTES)
            database = root / "signatures"
            database.mkdir()
            scanner = real_scanner or "/fixture-scanner"
            observed = []

            if real_scanner:
                # A local-only, deterministic ClamAV signature database avoids
                # remote FreshClam downloads and never affects user databases.
                (database / "eicar.ndb").write_text(
                    "Eicar-Test-Signature:0:*:" + EICAR_BYTES.hex() + "\n",
                    encoding="ascii",
                )

            def scanner_double(command, timeout):
                observed.append((tuple(command), timeout))
                self.assertEqual(Path(command[-1]).read_bytes(), EICAR_BYTES)
                return subprocess.CompletedProcess(
                    command, 1, f"{selected}: Eicar-Test-Signature FOUND\n", ""
                )

            with ExitStack() as stack:
                stack.enter_context(patch.object(gate, "DATABASE", database))
                stack.enter_context(patch.object(gate, "CACHE_DB", root / "cache.sqlite3"))
                stack.enter_context(patch.object(gate, "SCAN_REQUEST_DB", root / "requests.sqlite3"))
                stack.enter_context(patch.object(
                    gate, "intended_destination", return_value="com.example.viewer"
                ))
                stack.enter_context(patch.object(
                    gate, "pdf_fallback_application", return_value=None
                ))
                stack.enter_context(patch.object(gate, "record_scan_destination"))
                stack.enter_context(patch.object(gate, "verify_local_file_available"))
                stack.enter_context(patch.object(
                    gate, "read_signature_database_version", return_value="fixture"
                ))
                verify_target = stack.enter_context(patch.object(gate, "verify_launch_target"))
                quarantine = stack.enter_context(patch.object(gate, "remove_quarantine"))
                launch = stack.enter_context(patch.object(gate, "launch_clean_file"))
                if not real_scanner:
                    stack.enter_context(patch.object(
                        gate, "run_scan_command", side_effect=scanner_double
                    ))
                with self.assertRaisesRegex(
                    RuntimeError, "^Malware was detected; opening was stopped\\.$"
                ) as blocked:
                    gate.scan_and_open(
                        str(selected), scanner, protection_level="standard"
                    )
                self.assertTrue(any(
                    name.startswith("Eicar-Test-Signature")
                    for name in blocked.exception.scan_result.detection_names
                ))
                self.assertNotIn(str(selected), str(blocked.exception))
                verify_target.assert_not_called()
                quarantine.assert_not_called()
                launch.assert_not_called()
                self.assertFalse(gate.cached_clean(gate.cache_key(
                    gate.fingerprint(selected), True
                )))
                self.assertEqual(selected.read_bytes(), EICAR_BYTES)
                if not real_scanner:
                    self.assertEqual(len(observed), 1)
                    command, timeout = observed[0]
                    self.assertEqual(command[0], scanner)
                    self.assertEqual(command[-2:], ("--", str(selected)))
                    self.assertIn("--database=" + str(database), command)
                    self.assertIn("--alert-encrypted=yes", command)
                    self.assertIn("--alert-exceeds-max=yes", command)
                    self.assertEqual(timeout, gate.PDF_SCAN_TIMEOUT)

    def test_standard_baseline_blocks_eicar_without_opening_or_caching(self):
        self.exercise_mandatory_gate()

    @unittest.skipUnless(
        os.environ.get("PDF_MAGIC_EICAR_CLAMAV"),
        "Real ClamAV integration runs in the dedicated CI fixture job",
    )
    def test_real_clamav_blocks_eicar_at_the_same_gate(self):
        scanner = os.environ["PDF_MAGIC_EICAR_CLAMAV"]
        self.assertTrue(Path(scanner).is_absolute())
        self.assertTrue(Path(scanner).is_file())
        self.exercise_mandatory_gate(real_scanner=scanner)


if __name__ == "__main__":
    unittest.main()
