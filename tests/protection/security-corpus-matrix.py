#!/usr/bin/env python3
"""opener-1048: exercise the security corpus against every defined profile contract.

Standard, Enhanced and Maximum remain non-selectable. Each actual fixture is
passively inspected and separately submitted to all three policy-admission
boundaries; rejection is not a simulated successful antivirus scan. The
deployed Built-in gate has its own scanner-verdict integration suite.
"""

from hashlib import sha256
import importlib
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from effective_protection_policy import (
    ACTIVE_PROFILE_ID,
    SELECTED_PROFILE_KEY,
    UnsupportedEffectivePolicy,
    resolve_effective_policy,
)
from pdf_structure_parser import parse_pdf_structure_result
from protection_policy_definitions import (
    BASELINE_CONTROLS,
    ControlAvailability,
    FailureDisposition,
    PROTECTION_POLICIES,
)
from protection_profiles import (
    BASELINE_SAFETY_CHECKS,
    PROTECTION_PROFILES,
    ProtectionProfileID,
)


ROOT = Path(__file__).resolve().parents[2]

# Enumerate the real fixture producers, not copied samples or synthetic verdicts.
# Retain the six baseline documents independently of the adversarial families.
COLLECTIONS = {
    "reference": ("reference_pdf_collection", "REFERENCE_PDFS", "identifier"),
    "incorrectly-named": ("reference_pdf_collection", "INCORRECTLY_NAMED_FILES", "filename"),
    "invalid-header": ("reference_pdf_collection", "INVALID_PDF_HEADERS", "identifier"),
    "incremental": ("reference_pdf_collection", "INCREMENTAL_REFERENCE_PDFS", "identifier"),
    "malformed-xref": ("malformed_xref_pdf_collection", "MALFORMED_XREF_PDFS", "identifier"),
    "valid-object-stream": ("malformed_object_stream_corpus", "VALID_OBJECT_STREAM_PDFS", "identifier"),
    "malformed-object-stream": ("malformed_object_stream_corpus", "MALFORMED_OBJECT_STREAM_PDFS", "identifier"),
    "encrypted": ("encrypted_pdf_collection", "ENCRYPTED_REFERENCE_PDFS", "identifier"),
    "javascript": ("javascript_action_corpus", "JAVASCRIPT_ACTION_PDFS", "identifier"),
    "external-launch": ("external_launch_action_corpus", "EXTERNAL_LAUNCH_PDFS", "identifier"),
    "embedded-file": ("embedded_file_corpus", "EMBEDDED_FILE_PDFS", "identifier"),
    "interactive-form": ("interactive_form_corpus", "INTERACTIVE_FORM_PDFS", "identifier"),
    "oversized-stream": ("oversized_stream_corpus", "OVERSIZED_STREAM_PDFS", "identifier"),
    "large-valid": ("large_valid_pdf_corpus", "LARGE_VALID_PDF_CASES", "identifier"),
    "memory-stress": ("memory_stress_pdf_corpus", "MEMORY_STRESS_PDFS", "identifier"),
    "deep-reference": ("deep_object_reference_corpus", "SECURITY_REFERENCE_PDFS", "identifier"),
}
TRACKED = {
    "truncated": ROOT / "tests/fixtures/pdf-security-corpus/truncated",
    "parser-timeouts": ROOT / "tests/fixtures/pdf-security-corpus/parser-timeouts",
}
EMPTY_FILENAMES = ("empty", "empty.pdf", "empty.txt")
EXPECTED_FAMILIES = set(COLLECTIONS) | set(TRACKED) | {"digital-signature", "empty"}


def corpus_cases():
    """Yield each fixture once; large/stress cases are generated on demand."""
    for family, (module_name, collection_name, identifier_name) in COLLECTIONS.items():
        module = importlib.import_module(module_name)
        cases = getattr(module, collection_name)
        for case in cases:
            if family == "large-valid":
                content = module.build_large_valid_pdf(case)
            elif family == "memory-stress":
                content = case.generate()
            else:
                content = case.content
            yield family, getattr(case, identifier_name), content

    # Synthetic, test-only signing keys stay in memory; no private key file is read.
    from digital_signature_corpus import signed_pdf_corpus
    for case in signed_pdf_corpus():
        yield "digital-signature", case.identifier, case.content

    for family, directory in TRACKED.items():
        for path in sorted(directory.glob("*.pdf")):
            yield family, path.name, path.read_bytes()

    for name in EMPTY_FILENAMES:
        yield "empty", name, (ROOT / "tests/fixtures" / name).read_bytes()


class SecurityCorpusProfileMatrixTests(unittest.TestCase):
    def test_every_fixture_crosses_every_profile_admission_boundary(self):
        self.assertEqual(set(PROTECTION_PROFILES), set(ProtectionProfileID))
        self.assertEqual(set(PROTECTION_POLICIES), set(ProtectionProfileID))
        expected = []
        tested = {profile: [] for profile in ProtectionProfileID}
        seen = set()

        for family, identifier, content in corpus_cases():
            with self.subTest(family=family, fixture=identifier):
                key = (family, identifier)
                self.assertNotIn(key, seen, "Every security fixture must run once")
                seen.add(key)
                self.assertIs(type(content), bytes)
                fingerprint = sha256(content).hexdigest()
                expected.append((family, identifier, fingerprint))

                # A bounded, passive parsing result is never an opening verdict.
                evidence = parse_pdf_structure_result(content)
                self.assertIs(evidence.to_dict()["authorizesOpen"], False)

                for profile in ProtectionProfileID:
                    with self.subTest(profile=profile.value):
                        definition = PROTECTION_PROFILES[profile]
                        policy = PROTECTION_POLICIES[profile]
                        self.assertEqual(definition.identifier, profile)
                        self.assertEqual(policy.profile_id, profile)
                        self.assertFalse(definition.selectable)
                        self.assertFalse(policy.selectable)
                        self.assertIs(policy.failure_disposition, FailureDisposition.DENY)
                        self.assertTrue(BASELINE_SAFETY_CHECKS.issubset(
                            definition.required_safety_checks
                        ))
                        current = {
                            check.control for check in policy.required_checks
                            if check.availability is ControlAvailability.CURRENT
                        }
                        self.assertEqual(current, set(BASELINE_CONTROLS))

                        preferences = {
                            SELECTED_PROFILE_KEY: profile.value,
                            "customPDFBrowser": "preserve-custom-viewer",
                            "showScanProgress": False,
                        }
                        unchanged = dict(preferences)
                        # Profile admission must fail before ANY scanner, launch,
                        # quarantine or filesystem-changing subprocess is possible.
                        with patch.object(subprocess, "run") as run, patch.object(
                            subprocess, "Popen"
                        ) as process:
                            with self.assertRaises(UnsupportedEffectivePolicy):
                                resolve_effective_policy(preferences)
                            run.assert_not_called()
                            process.assert_not_called()
                        self.assertEqual(preferences, unchanged)
                        tested[profile].append((family, identifier, fingerprint))

                self.assertEqual(sha256(content).hexdigest(), fingerprint)

        self.assertEqual({family for family, _ in seen}, EXPECTED_FAMILIES)
        self.assertGreaterEqual(len(expected), 70, "The full corpus must not shrink")
        for profile in ProtectionProfileID:
            self.assertEqual(tested[profile], expected)
        self.assertEqual(
            sum(len(rows) for rows in tested.values()),
            len(expected) * len(ProtectionProfileID),
        )

    def test_builtin_remains_only_effective_policy_and_ci_runs_matrix(self):
        effective = resolve_effective_policy({
            SELECTED_PROFILE_KEY: ACTIVE_PROFILE_ID,
            "customPDFBrowser": "preserve-custom-viewer",
            "showScanProgress": False,
        })
        self.assertEqual(effective.profile_id, "built-in")
        self.assertEqual(set(effective.required_checks), set(BASELINE_CONTROLS))
        self.assertIs(effective.failure_disposition, FailureDisposition.DENY)
        self.assertFalse(effective.optional_checks)

        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "PYTHONPATH=. python3 tests/protection/security-corpus-matrix.py -v", ci
        )
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("security_corpus_matrix", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("verify_file_integrity", scanner)
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("tests/fixtures/pdf-security-corpus/** export-ignore", attributes)


if __name__ == "__main__":
    unittest.main()
