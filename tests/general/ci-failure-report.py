#!/usr/bin/env python3
"""Portable contract tests for CI failure reporting, with no GitHub token."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci_failure_report.py"
spec = importlib.util.spec_from_file_location("ci_failure_report", SCRIPT)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class FailureReportTests(unittest.TestCase):
    def test_failed_job_and_exact_step_links(self):
        jobs = [{
            "name": "PDF structure (Ubuntu)", "conclusion": "failure",
            "html_url": "https://github.com/PDF-magic/opener/actions/runs/123/job/456",
            "steps": [
                {"name": "Set up", "number": 1, "conclusion": "success"},
                {"name": "Check malformed PDFs", "number": 2, "conclusion": "failure"},
            ],
        }]
        output = report.render_report("PDF-magic/opener", "123", jobs)
        self.assertIn("PDF structure (Ubuntu)", output)
        self.assertIn("job/456#step:2:1", output)
        self.assertIn("Check malformed PDFs", output)
        self.assertNotIn("Set up", output)

    def test_skipped_and_successful_jobs_are_not_presented_as_failures(self):
        jobs = [
            {"name": "Skipped test", "conclusion": "skipped"},
            {"name": "Healthy test", "conclusion": "success"},
        ]
        output = report.render_report("PDF-magic/opener", "123", jobs)
        self.assertNotIn("Skipped test", output)
        self.assertNotIn("Healthy test", output)
        self.assertIn("No failed job metadata", output)

    def test_cancelled_runner_without_steps_has_actionable_fallback(self):
        output = report.render_report("PDF-magic/opener", "123", [
            {"name": "macOS", "conclusion": "cancelled", "steps": []},
        ])
        self.assertIn("macOS", output)
        self.assertIn("No failed step recorded", output)
        self.assertIn("/actions/runs/123", output)

    def test_bad_job_url_cannot_become_external_link(self):
        output = report.render_report("PDF-magic/opener", "123", [{
            "name": "[unsafe](example)", "conclusion": "failure",
            "html_url": "https://example.net/steal",
            "steps": [{"name": "Broken | step", "number": 2, "conclusion": "failure"}],
        }])
        self.assertNotIn("https://example.net", output)
        self.assertIn("\\[unsafe\\]", output)
        self.assertIn("Broken \\| step", output)

    def test_details_are_bounded(self):
        jobs = [{"name": f"failure-{i}", "conclusion": "failure",
                 "steps": [{"name": f"step-{j}", "conclusion": "failure", "number": j + 1}
                           for j in range(12)]} for i in range(35)]
        output = report.render_report("PDF-magic/opener", "123", jobs)
        self.assertIn("5 more failed jobs", output)
        self.assertIn("4 more failed steps", output)
        self.assertNotIn("failure-34", output)

    def test_pagination_requests_only_job_metadata(self):
        requests = []
        class Response:
            def __init__(self, data):
                self.data = data
            def __enter__(self):
                return self
            def __exit__(self, *_):
                pass
            def read(self):
                return self.data
        import json
        def fake_open(request, timeout):
            requests.append(request.full_url)
            count = 100 if len(requests) == 1 else 1
            return Response(json.dumps({"jobs": [{"id": i} for i in range(count)]}).encode())
        with patch.object(report.urllib.request, "urlopen", fake_open):
            jobs = report.fetch_jobs("PDF-magic/opener", "123", "2", "token")
        self.assertEqual(len(jobs), 101)
        self.assertIn("/attempts/2/jobs?", requests[0])
        self.assertIn("page=2", requests[1])
        self.assertEqual(len(requests), 2)


if __name__ == "__main__":
    unittest.main()
