#!/usr/bin/env python3
"""No-document, no-network ClamAV feature-probe regression coverage."""

from dataclasses import FrozenInstanceError
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import scanner_feature_check as features

ROOT = Path(__file__).resolve().parent


def help_text(options):
    return "ClamAV scanner options\n --help             Show help\n" + "".join(
        f"  {option}[=yes/no]  Available option\n" for option in options
    )


class ScannerFeatureCheckTests(unittest.TestCase):
    def test_reports_only_exact_advertised_capabilities_and_required_flags(self):
        output = help_text(features.GATE_OPTIONS | {"--scan-pdf", "--scan-archive", "--scan-pe"})
        with patch.object(features.subprocess, "run", return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout=output, stderr=""
        )) as run:
            result = features.inspect_scanner_features("/opt/homebrew/bin/clamscan")
        run.assert_called_once_with(
            ["/opt/homebrew/bin/clamscan", "--help"], capture_output=True,
            text=True, timeout=features.HELP_TIMEOUT, check=False,
        )
        self.assertTrue(result.inspected)
        self.assertTrue(result.advertises_gate_options)
        self.assertEqual(result.missing_gate_options, frozenset())
        self.assertEqual(result.supported_features, frozenset({"pdf", "archives", "pe"}))
        self.assertIn("mail", result.unsupported_features)
        self.assertNotIn("mail", result.supported_features)
        with self.assertRaises(FrozenInstanceError):
            result.inspected = False

    def test_help_aliases_and_near_matches_never_fake_a_feature(self):
        output = ("  -r, --recursive[=yes/no]  Recursive\n"
                  "  --help  Show help\n"
                  "  --scan-pdf-other=yes  Not PDF scanning\n"
                  "Examples might say --scan-pdf in a paragraph\n"
                  "  --scan-archive[=yes/no]  Archive mode\n")
        with patch.object(features.subprocess, "run", return_value=subprocess.CompletedProcess(
            [], 0, output, ""
        )):
            result = features.inspect_scanner_features("/mock/clamscan")
        self.assertTrue(result.inspected)
        self.assertNotIn("pdf", result.supported_features)
        self.assertIn("archives", result.supported_features)
        self.assertIn("--recursive", result.supported_gate_options)
        self.assertFalse(result.advertises_gate_options)
        self.assertIn("--alert-encrypted", result.missing_gate_options)

    def test_failed_probes_are_unknown_not_unsupported(self):
        cases = [
            subprocess.CompletedProcess([], 1, help_text(features.GATE_OPTIONS), ""),
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, "Unknown program\n", ""),
            subprocess.CompletedProcess([], 0, help_text(features.GATE_OPTIONS), "warning"),
            subprocess.CompletedProcess([], 0, "x" * (features.MAX_HELP_LENGTH + 1), ""),
        ]
        for response in cases:
            with self.subTest(response=response.returncode), patch.object(
                features.subprocess, "run", return_value=response
            ):
                result = features.inspect_scanner_features("/mock/clamscan")
                self.assertFalse(result.inspected)
                self.assertEqual(result.unsupported_features, frozenset())
                self.assertEqual(result.missing_gate_options, frozenset())
                self.assertFalse(result.advertises_gate_options)
        for error in (FileNotFoundError(), PermissionError(),
                      subprocess.TimeoutExpired(cmd=["clamscan", "--help"], timeout=5),
                      UnicodeError()):
            with self.subTest(error=type(error).__name__), patch.object(
                features.subprocess, "run", side_effect=error
            ):
                self.assertFalse(features.inspect_scanner_features("/mock/clamscan").inspected)

    def test_rejects_paths_that_could_be_interpreted_as_options(self):
        for value in ("clamscan", "--version", "", None, b"/tmp/clamscan",
                      "/tmp/clam\x00scan", "a" * 4097):
            with self.subTest(value=repr(value)), patch.object(features.subprocess, "run") as run:
                with self.assertRaises(ValueError):
                    features.inspect_scanner_features(value)
                run.assert_not_called()

    def test_cli_is_path_free_and_does_not_authorize_open(self):
        output = help_text(features.GATE_OPTIONS | {"--scan-pdf"})
        with patch.object(features.subprocess, "run", return_value=subprocess.CompletedProcess(
            [], 0, output, ""
        )):
            self.assertEqual(features.main(["/mock/clamscan"]), 0)
        with patch.object(features.subprocess, "run", side_effect=OSError()):
            self.assertEqual(features.main(["/mock/clamscan"]), 1)

    def test_installed_scan_gate_and_configuration_remain_unchanged(self):
        gate = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("from scanner_feature_check import", gate)
        self.assertIn("scanner = scanner_path()", gate)
        self.assertIn("check_database()", gate)
        self.assertIn("if not cached_clean(cache_id):", gate)
        self.assertIn("'--alert-exceeds-max=yes', '--alert-encrypted=yes'", gate)
        self.assertIn("verify_file_integrity(path, before, identity)", gate)
        self.assertIn("launch_clean_file(path, target_app=", gate)
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 test-scanner-feature-check.py -v", ci)
        self.assertIn("python3 test-scan-and-open.py -v", ci)
        self.assertIn("macos-build:", ci)


if __name__ == "__main__":
    unittest.main()
