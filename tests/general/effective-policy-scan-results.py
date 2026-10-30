#!/usr/bin/env python3
"""Verify actual enforced scan policy is recorded on every available scan result.

The installed gate is Built-in; caller protection_level is request metadata.
No future/planned profile is activated or used to authorize opening.
"""
from dataclasses import FrozenInstanceError, asdict, fields, replace
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from effective_protection_policy import (
    ACTIVE_PROFILE_ID, SELECTED_PROFILE_KEY, UnsupportedEffectivePolicy,
    resolve_effective_policy,
)
from scan_results import EFFECTIVE_POLICY_ID, ScanResult

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("scan_and_open", ROOT / "scan-and-open.py")
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)


class EffectivePolicyScanResultsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / "sample.pdf"
        self.file.write_bytes(b"%PDF-1.4\nVerified sample")
        for name, value in (
            ("CACHE_DB", Path(self.temp.name) / "cache.sqlite3"),
            ("SCAN_REQUEST_DB", Path(self.temp.name) / "requests.sqlite3"),
        ):
            mocked = patch.object(opener, name, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        for name, value in (
            ("verify_launch_target", None),
            ("remove_quarantine", None),
            ("launch_clean_file", None),
            ("scan_engine_version", None),
        ):
            mocked = patch.object(opener, name, return_value=value)
            mocked.start()
            self.addCleanup(mocked.stop)

    def test_constant_is_actual_built_in_policy_not_planned_tier(self):
        self.assertEqual(EFFECTIVE_POLICY_ID, "built-in")
        self.assertEqual(EFFECTIVE_POLICY_ID, ACTIVE_PROFILE_ID)
        self.assertEqual(EFFECTIVE_POLICY_ID, resolve_effective_policy().profile_id)
        self.assertEqual(EFFECTIVE_POLICY_ID, resolve_effective_policy({
            SELECTED_PROFILE_KEY: ACTIVE_PROFILE_ID,
            "customBrowser": "unchanged",
        }).profile_id)
        for planned in ("standard", "enhanced", "maximum", None):
            with self.subTest(unsupported=planned), \
                    self.assertRaises(UnsupportedEffectivePolicy):
                resolve_effective_policy({SELECTED_PROFILE_KEY: planned})
        self.assertEqual(opener.EFFECTIVE_POLICY_ID, EFFECTIVE_POLICY_ID)
        for receipt in (
            ScanResult(),
            ScanResult(("Eicar-Test-Signature",)),
            ScanResult.from_clamav_output("private: Eicar-Test-Signature FOUND"),
            opener.CleanScanResult("clean", False),
            opener.CleanScanResult("clean", True),
        ):
            with self.subTest(receipt=type(receipt).__name__):
                self.assertEqual(receipt.effective_policy_id, "built-in")
                self.assertEqual(asdict(receipt)["effective_policy_id"], "built-in")
                self.assertFalse(next(f for f in fields(receipt)
                                      if f.name == "effective_policy_id").init)
                with self.assertRaises(FrozenInstanceError):
                    receipt.effective_policy_id = "maximum"
                with self.assertRaises(ValueError):
                    replace(receipt, effective_policy_id="maximum")
        for construct, args in (
            (ScanResult, ()),
            (opener.CleanScanResult, ("clean", False)),
        ):
            with self.assertRaises(TypeError):
                construct(*args, effective_policy_id="enhanced")

    def test_fresh_and_cached_scans_record_same_effective_policy(self):
        raw = subprocess.CompletedProcess([], 0, "sample: OK", "")
        with patch.object(opener.subprocess, "run", return_value=raw) as run:
            first = opener.scan_and_open(
                str(self.file), "/scanner", protection_level="maximum")
            cached = opener.scan_and_open(
                str(self.file), "/scanner", protection_level="unsupported-custom-profile")
        self.assertFalse(first.from_cache)
        self.assertTrue(cached.from_cache)
        self.assertEqual(first.status, cached.status)
        self.assertEqual(first.effective_policy_id, "built-in")
        self.assertEqual(cached.effective_policy_id, "built-in")
        self.assertEqual(asdict(first)["effective_policy_id"], "built-in")
        self.assertEqual(asdict(cached)["effective_policy_id"], "built-in")
        self.assertEqual(sum(c.args[0][0] == "/scanner" for c in run.call_args_list), 1)
        self.assertTrue(opener.cached_clean(opener.cache_key(
            opener.fingerprint(self.file), True)))

    def test_blocked_detection_and_incomplete_scans_carry_effective_policy(self):
        for index, (code, evidence) in enumerate((
            (1, "private: Eicar-Test-Signature FOUND"),
            (2, "private: error"),
            (0, "private: Empty file"),
        )):
            self.file.write_bytes(b"%PDF-1.4\n" + bytes([index]))
            raw = subprocess.CompletedProcess([], code, evidence, "")
            with self.subTest(code=code, evidence=evidence), \
                    patch.object(opener.subprocess, "run", return_value=raw) as run, \
                    patch.object(opener, "remove_quarantine") as remove, \
                    patch.object(opener, "launch_clean_file") as launch:
                with self.assertRaises(RuntimeError) as caught:
                    opener.scan_and_open(
                        str(self.file), "/scanner", protection_level="standard")
                result = caught.exception.scan_result
                self.assertIsInstance(result, ScanResult)
                self.assertEqual(result.effective_policy_id, "built-in")
                self.assertEqual(asdict(result)["effective_policy_id"], "built-in")
                if index == 0:
                    self.assertEqual(result.detection_names,
                                     ("Eicar-Test-Signature",))
                self.assertEqual(run.call_count, 1)
                remove.assert_not_called()
                launch.assert_not_called()
                self.assertFalse(opener.cached_clean(opener.cache_key(
                    opener.fingerprint(self.file), True)))

    def test_launch_failure_retains_effective_policy_on_receipt(self):
        raw = subprocess.CompletedProcess([], 0, "sample: OK", "")
        with patch.object(opener.subprocess, "run", return_value=raw), \
                patch.object(opener, "launch_clean_file",
                             side_effect=OSError("destination not installed")):
            with self.assertRaises(opener.LaunchFailedError) as caught:
                opener.scan_and_open(str(self.file), "/scanner",
                                     protection_level="enhanced")
        self.assertEqual(caught.exception.scan_result.status, "clean")
        self.assertEqual(caught.exception.scan_result.effective_policy_id, "built-in")
        with patch.object(opener.subprocess, "run") as scan, \
                patch.object(opener, "launch_clean_file",
                             side_effect=OSError("still missing")):
            with self.assertRaises(opener.LaunchFailedError) as cached:
                opener.scan_and_open(str(self.file), "/scanner")
        self.assertTrue(cached.exception.scan_result.from_cache)
        self.assertEqual(cached.exception.scan_result.effective_policy_id, "built-in")
        scan.assert_not_called()

    def test_metadata_is_not_a_policy_switch_or_private_audit_record(self):
        policy = (ROOT / "protection_policy_definitions.py").read_text(encoding="utf-8")
        source = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertIn("not an executable scan policy", policy.lower())
        self.assertNotIn("from protection_policy_definitions import", source)
        self.assertNotIn("from protection_profiles import", source)
        self.assertIn("if not cached_clean(cache_id):", source)
        self.assertIn("decision = decide_opening(detection)", source)
        self.assertIn("verify_file_integrity(path, before, identity)", source)
        self.assertIn("scan_result = (CleanScanResult(", source)
        self.assertIn("failure.scan_result = ScanResult(decision.detection_names)", source)
        self.assertNotIn("effective_policy_id TEXT", source)
        self.assertIn("python3 scripts/run-test.py tests/general/effective-policy-scan-results.py -v",
                      (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
