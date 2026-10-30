#!/usr/bin/env python3
"""Regression tests for the conservative CI dependency map."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from ci_test_scope import ALL_GROUPS, select_groups


class CITestScopeTests(unittest.TestCase):
    def test_documentation_only_changes_skip_specialized_groups(self):
        self.assertEqual(select_groups(["README.md"]), frozenset())
        self.assertEqual(select_groups(["docs/security-overview.md"]), frozenset())

    def test_documentation_with_direct_test_dependencies_selects_its_group(self):
        self.assertEqual(select_groups(["docs/maximum/renderer-selection.md"]), {"maximum"})
        self.assertEqual(select_groups(["docs/pdf-parser-evaluation.md"]), {"pdf"})

    def test_pdf_and_policy_changes_select_related_suites(self):
        self.assertEqual(select_groups(["test-pdf-form-actions.py"]), {"pdf"})
        self.assertEqual(select_groups(["test-enhanced-analysis-findings.py"]), {"pdf", "policy"})
        self.assertEqual(select_groups(["test-protection-exception-reason.py"]), {"policy"})

    def test_native_maximum_changes_select_portable_and_macos_tests(self):
        self.assertEqual(select_groups(["maximum_sanitized_copy.py"]), {"maximum", "macos"})
        self.assertEqual(select_groups(["test-maximum-isolated-renderer.py"]), {"maximum", "macos"})

    def test_shared_security_and_workflow_changes_select_every_suite(self):
        for path in (
            "scan-and-open.py", "protection_policy_definitions.py",
            "requirements-enhanced-pdf.txt", ".github/workflows/ci.yml",
            "scripts/ci_test_scope.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(select_groups([path]), ALL_GROUPS)

    def test_unclassified_and_empty_changes_fail_safe_to_full_suite(self):
        self.assertEqual(select_groups(["new-security-module.py"]), ALL_GROUPS)
        self.assertEqual(select_groups([]), ALL_GROUPS)


if __name__ == "__main__":
    unittest.main()
