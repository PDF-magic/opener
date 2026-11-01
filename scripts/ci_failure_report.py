#!/usr/bin/env python3
"""Publish bounded, metadata-only GitHub Actions failure details.

Do not download test logs or upload test fixtures: either could expose scanned
PDF contents or runner/user state. Job and step results link to GitHub's own
access-controlled logs instead.
"""

import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

FAILED = frozenset({"failure", "timed_out", "cancelled", "action_required"})
MAX_PAGES = 10
MAX_JOBS = 30
MAX_STEPS = 8


def safe_label(value):
    """Make job-controlled labels safe as one-line Markdown link text."""
    value = re.sub(r"\s+", " ", str(value or "unnamed")).strip()
    for char in ("\\", "[", "]", "|", chr(96), "<", ">"):
        value = value.replace(char, "\\" + char)
    return value[:180]


def fetch_jobs(repository, run_id, attempt, token):
    """Fetch only job/step metadata, never logs or build artifacts."""
    jobs = []
    for page in range(1, MAX_PAGES + 1):
        url = (
            f"https://api.github.com/repos/{repository}/actions/runs/{run_id}/"
            f"attempts/{attempt}/jobs?per_page=100&page={page}"
        )
        request = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "pdf-magic-ci-failure-report",
        })
        with urllib.request.urlopen(request, timeout=15) as response:
            batch = json.load(response).get("jobs", [])
        jobs.extend(batch)
        if len(batch) < 100:
            break
    return jobs


def render_report(repository, run_id, jobs):
    """Summarize failed jobs and their failed steps with links to exact logs."""
    run_url = f"https://github.com/{repository}/actions/runs/{run_id}"
    lines = [
        "## CI test-failure details",
        "",
        f"[Open workflow run and logs]({run_url})",
        "",
        "This report contains only GitHub job/step status metadata, not test logs,",
        "PDF fixtures, or local configuration.",
        "",
    ]
    failures = [job for job in jobs if job.get("conclusion") in FAILED]
    if not failures:
        lines.append("No failed job metadata was available. Inspect the workflow run for details.")
    for job in failures[:MAX_JOBS]:
        job_url = job.get("html_url") or ""
        if not job_url.startswith(f"https://github.com/{repository}/actions/"):
            job_url = run_url
        outcome = safe_label(job.get("conclusion"))
        lines.append(f"- **[{safe_label(job.get('name'))}]({job_url})** — {outcome}")
        failed_steps = [step for step in job.get("steps", [])
                        if step.get("conclusion") in FAILED]
        for step in failed_steps[:MAX_STEPS]:
            number = step.get("number")
            step_url = f"{job_url}#step:{number}:1" if isinstance(number, int) and number > 0 and job_url != run_url else job_url
            lines.append(
                f"  - [{safe_label(step.get('name'))}]({step_url})"
                f" — {safe_label(step.get('conclusion'))}"
            )
        if len(failed_steps) > MAX_STEPS:
            lines.append(f"  - …and {len(failed_steps) - MAX_STEPS} more failed steps (see job logs)")
        if not failed_steps:
            lines.append("  - No failed step recorded; inspect the job for setup or runner errors.")
    if len(failures) > MAX_JOBS:
        lines.append(f"- …and {len(failures) - MAX_JOBS} more failed jobs (see workflow run)")
    return "\n".join(lines) + "\n"


def main():
    repository = os.environ["GITHUB_REPOSITORY"]
    run_id = os.environ["GITHUB_RUN_ID"]
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    token = os.environ["GH_TOKEN"]
    try:
        jobs = fetch_jobs(repository, run_id, attempt, token)
        report = render_report(repository, run_id, jobs)
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError):
        report = render_report(repository, run_id, [])
    path = Path(os.environ["RUNNER_TEMP"]) / "ci-test-failures.md"
    path.write_text(report, encoding="utf-8")
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as output:
        output.write(report)
    print(report)


if __name__ == "__main__":
    main()
