#!/usr/bin/env python3
"""opener-0306: real separate-process PDF parser isolation regressions."""
from dataclasses import FrozenInstanceError
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from pypdf import PdfWriter

import maximum_isolated_analysis as isolated


def sample_pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class MaximumIsolatedAnalysisTests(unittest.TestCase):
    def test_each_complex_inspection_runs_outside_parent_process(self):
        pdf = sample_pdf()
        for name, expected in (
            ("structureAmbiguity", ("inspected_objects",)),
            ("malformedStructures", ("object_count", "page_count")),
            ("decompressionRequirements", ("stream_count", "flate_stream_count",
                                           "decoded_bytes", "maximum_expansion_ratio")),
        ):
            with self.subTest(inspection=name):
                report = isolated.run_isolated_pdf_analysis(pdf, name)
                self.assertNotEqual(report.worker_pid, os.getpid())
                self.assertGreater(report.worker_pid, 0)
                self.assertEqual(tuple(key for key, _ in report.metrics), expected)
                self.assertFalse(report.permits_open)
                self.assertIs(report.to_dict()["permitsOpen"], False)
                with self.assertRaises(FrozenInstanceError):
                    report.permits_open = True

    def test_input_is_raw_bytes_not_path_and_worker_is_isolated_python(self):
        document = sample_pdf()
        real_run = subprocess.run
        captured = []
        def invoke(command, **kwargs):
            captured.append((tuple(command), kwargs.copy()))
            return real_run(command, **kwargs)
        with patch.object(isolated.subprocess, "run", side_effect=invoke):
            isolated.run_isolated_pdf_analysis(document, "malformedStructures")
        cmd, opts = captured[0]
        self.assertEqual(cmd[0], sys.executable)
        self.assertEqual(cmd[1:3], ("-I", "-B"))
        self.assertEqual(cmd[-1], "malformedStructures")
        self.assertTrue(cmd[-2].endswith("maximum_isolated_worker.py"))
        self.assertIs(opts["input"], document)
        self.assertIs(opts["stderr"], subprocess.DEVNULL)
        self.assertFalse(opts["check"])
        self.assertTrue(opts["start_new_session"])
        self.assertTrue(opts["close_fds"])
        self.assertEqual(opts["cwd"], "/")
        self.assertEqual(opts["timeout"], isolated.WORKER_WALL_TIMEOUT_SECONDS)
        self.assertEqual(set(opts["env"]),
                         {"PATH", "HOME", "LANG", "PYTHONDONTWRITEBYTECODE",
                          "PYTHONNOUSERSITE"})

    def test_malformed_pdf_blocks_without_exposing_payload(self):
        for name in isolated._INSPECTORS:
            with self.subTest(name=name):
                with self.assertRaises(isolated.IsolatedPDFAnalysisError) as err:
                    isolated.run_isolated_pdf_analysis(b"%PDF-1.4\nPrivate secret", name)
                self.assertEqual(str(err.exception), isolated.BLOCK_MESSAGE)
                self.assertNotIn("Private", str(err.exception))

    def test_invalid_or_oversized_input_rejected_without_starting_child(self):
        with patch.object(isolated.subprocess, "run") as invoke:
            for payload, stage in (
                (b"", "structureAmbiguity"), ("not bytes", "structureAmbiguity"),
                (bytearray(sample_pdf()), "structureAmbiguity"),
                (b"%PDF" * (isolated.MAX_PDF_BYTES // 4 + 1), "malformedStructures"),
                (sample_pdf(), "arbitrary_module"), (sample_pdf(), ""),
                (sample_pdf(), None), (sample_pdf(), "../etc/passwd"),
            ):
                with self.subTest(stage=stage), self.assertRaises(
                    isolated.IsolatedPDFAnalysisError
                ):
                    isolated.run_isolated_pdf_analysis(payload, stage)
            invoke.assert_not_called()

    def test_nonzero_exit_crash_and_timeout_fail_closed(self):
        exceptions = (subprocess.TimeoutExpired("worker", 1),
                      OSError("sensitive path"),
                      RuntimeError("private diagnostics"))
        for failure in exceptions:
            with self.subTest(error=type(failure)), patch.object(
                isolated.subprocess, "run", side_effect=failure
            ), self.assertRaises(isolated.IsolatedPDFAnalysisError) as caught:
                isolated.run_isolated_pdf_analysis(sample_pdf(), "malformedStructures")
            self.assertEqual(str(caught.exception), isolated.BLOCK_MESSAGE)
        with patch.object(isolated.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 137, b"")):
            with self.assertRaises(isolated.IsolatedPDFAnalysisError):
                isolated.run_isolated_pdf_analysis(sample_pdf(), "malformedStructures")

    def test_untrusted_worker_output_is_never_an_open_verdict(self):
        valid = {
            "protocol": 1, "inspection": "malformedStructures",
            "workerPid": 321, "metrics": {"object_count": 4, "page_count": 1},
            "permitsOpen": False,
        }
        samples = [
            b"not-json", b"", b"X" * (isolated.MAX_RESPONSE_BYTES + 1),
            json.dumps({**valid, "permitsOpen": True}).encode(),
            json.dumps({**valid, "protocol": 2}).encode(),
            json.dumps({**valid, "inspection": "structureAmbiguity"}).encode(),
            json.dumps({**valid, "workerPid": True}).encode(),
            json.dumps({**valid, "workerPid": -1}).encode(),
            json.dumps({**valid, "metrics": {"object_count": 4, "page_count": True}}).encode(),
            json.dumps({**valid, "metrics": {"object_count": 4}}).encode(),
            json.dumps({**valid, "metrics": {"object_count": 4, "page_count": 1,
                                           "secret": "private"}}).encode(),
            b'{"protocol":1,"protocol":1,"inspection":"malformedStructures"}',
        ]
        for stdout in samples:
            with self.subTest(stdout=stdout[:30]), patch.object(
                isolated.subprocess, "run",
                return_value=subprocess.CompletedProcess([], 0, stdout),
            ), self.assertRaises(isolated.IsolatedPDFAnalysisError) as caught:
                isolated.run_isolated_pdf_analysis(sample_pdf(), "malformedStructures")
            self.assertEqual(str(caught.exception), isolated.BLOCK_MESSAGE)

    def test_child_rejects_unapproved_dispatch_and_input(self):
        child = Path(isolated.__file__).with_name("maximum_isolated_worker.py")
        for stage, payload in (("arbitrary_module", sample_pdf()),
                               ("structureAmbiguity", b"")):
            with self.subTest(stage=stage):
                result = subprocess.run(
                    [sys.executable, "-I", "-B", str(child), stage],
                    input=payload, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    timeout=15, cwd="/",
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")

    def test_response_cannot_be_mutated_or_include_source_data(self):
        result = isolated.run_isolated_pdf_analysis(sample_pdf(), "malformedStructures")
        d = result.to_dict()
        d["metrics"]["page_count"] = 999
        self.assertNotEqual(result.to_dict()["metrics"]["page_count"], 999)
        self.assertEqual(set(result.to_dict()), {
            "inspection", "workerPid", "metrics", "permitsOpen",
        })
        self.assertNotIn("payload", repr(result).lower())

    def test_installed_gate_and_profile_selection_unchanged(self):
        root = Path(__file__).resolve().parent
        scan = (root / "scan-and-open.py").read_text()
        self.assertNotIn("maximum_isolated_analysis", scan)
        self.assertNotIn("maximum_isolated_worker", scan)
        self.assertIn("if not cached_clean(cache_id):", scan)
        self.assertIn("remove_quarantine(path)", scan)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.MAXIMUM].selectable)
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
