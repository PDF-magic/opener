#!/usr/bin/env python3
"""Exercise Finder's genuine Open verb on macOS, only with explicit live opt-in.

Normal CI tests check the command and guardrails without launching Finder,
reading user documents, or changing any file associations.
"""

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
APP_ID = "local.studio.brave-pdf-opener"
SCRIPT = ROOT / "test-finder-open.applescript"
RUNTIME = (Path.home() / "Library/Application Support/Studio/allow-and-open")
IDENTIFY = RUNTIME / "identify-pdf-handler"
ORIGINS = RUNTIME / "scan-request-origins.jsonl"


def ensure_default_pdf_handler():
    """Require the configured scan gate; never set or replace the default."""
    result = subprocess.run(
        [str(IDENTIFY)], capture_output=True, check=True, timeout=10,
    )
    if result.stdout != (APP_ID + "\n").encode("ascii"):
        raise RuntimeError("PDF Magic Opener is not the current default PDF handler.")


def validate_test_pdf(path):
    """Only accept an existing regular local PDF that the operator supplied."""
    pdf = Path(path)
    if pdf.suffix.lower() != ".pdf" or pdf.is_symlink() or not pdf.is_file():
        raise ValueError("Supply an existing, regular, non-symlink PDF test file.")
    return pdf.resolve(strict=True)


def origin_log_size(path=ORIGINS):
    """Read only the byte offset for the anonymous scan-origin log."""
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return 0
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise RuntimeError("Cannot safely inspect the scan-origin log.")
    return metadata.st_size


def finder_request_received(path=ORIGINS, start=0, timeout=15):
    """Look only for newly appended anonymous Finder origin records."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if origin_log_size(path) > start:
                with path.open("rb") as stream:
                    stream.seek(start)
                    records = stream.read(32768).splitlines()
                for raw in records:
                    try:
                        record = json.loads(raw)
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if (record.get("from_finder") is True
                            and record.get("from_browser") is False
                            and record.get("from_desktop_application") is False):
                        return True
        except FileNotFoundError:
            pass
        time.sleep(0.1)
    return False


def live_finder_open(path):
    """Invoke Finder without changing macOS associations or touching PDF data."""
    if sys.platform != "darwin":
        raise RuntimeError("The live Finder Open test requires macOS.")
    pdf = validate_test_pdf(path)
    ensure_default_pdf_handler()
    if not (RUNTIME / "allow-and-open.sh").is_file():
        raise RuntimeError("PDF Magic Opener's scan gate is not installed.")
    before = origin_log_size()
    subprocess.run(
        ["/usr/bin/osascript", str(SCRIPT), str(pdf)],
        capture_output=True, check=True, timeout=30,
    )
    if not finder_request_received(start=before):
        raise RuntimeError("Finder Open did not produce a new Finder-attributed scan request.")
    print("PASS: Finder Open reached the installed PDF scan gate.")
    print("Inspect the native scan progress and normal allow/block outcome.")


class FinderOpenTests(unittest.TestCase):
    def test_finder_script_uses_real_open_verb_and_argv(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('tell application id "com.apple.finder"', source)
        self.assertIn("open requestedPDF", source)
        self.assertIn("POSIX file (item 1 of argv)", source)
        self.assertNotIn("do shell script", source)
        self.assertNotIn("setDefaultApplication", source)

    def test_handler_preflight_checks_actual_pdf_default(self):
        with patch("subprocess.run", return_value=subprocess.CompletedProcess(
                [], 0, (APP_ID + "\n").encode("ascii"), b"")) as run:
            ensure_default_pdf_handler()
        run.assert_called_once_with(
            [str(IDENTIFY)], capture_output=True, check=True, timeout=10)
        for actual in (b"com.apple.Preview\n", b"", b"com.google.Chrome\n"):
            with self.subTest(actual=actual), patch(
                    "subprocess.run", return_value=subprocess.CompletedProcess(
                        [], 0, actual, b"")):
                with self.assertRaisesRegex(RuntimeError, "not the current default"):
                    ensure_default_pdf_handler()

    def test_live_mode_refuses_to_change_default_or_read_pdf_on_non_macos(self):
        with patch.object(sys, "platform", "linux"), patch("subprocess.run") as run:
            with self.assertRaisesRegex(RuntimeError, "requires macOS"):
                live_finder_open("/tmp/untouched.pdf")
        run.assert_not_called()

    def test_invalid_pdf_is_rejected_without_invoking_finder(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "fixture.PDF"
            pdf.write_bytes(b"%PDF-1.4\n")
            self.assertEqual(validate_test_pdf(pdf), pdf.resolve())
            alias = root / "alias.pdf"
            alias.symlink_to(pdf)
            for candidate in (alias, root / "missing.pdf", root / "text.txt"):
                with self.subTest(candidate=candidate):
                    with self.assertRaises(ValueError):
                        validate_test_pdf(candidate)

    def test_only_new_finder_attributed_events_are_accepted(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "origin.jsonl"
            log.write_text(json.dumps({
                "from_finder": True, "from_browser": False,
                "from_desktop_application": False,
            }) + "\n", encoding="utf-8")
            before = origin_log_size(log)
            with patch("time.monotonic", side_effect=[0, 1]):
                self.assertFalse(finder_request_received(log, start=before, timeout=0.5))
            with log.open("a", encoding="utf-8") as out:
                out.write(json.dumps({
                    "from_finder": False, "from_browser": True,
                    "from_desktop_application": False,
                }) + "\n")
            with patch("time.monotonic", side_effect=[0, 1]):
                self.assertFalse(finder_request_received(log, start=before, timeout=0.5))
            with log.open("a", encoding="utf-8") as out:
                out.write(json.dumps({
                    "from_finder": True, "from_browser": False,
                    "from_desktop_application": False,
                }) + "\n")
            with patch("time.monotonic", side_effect=[0, 0.1]):
                self.assertTrue(finder_request_received(log, start=before, timeout=0.5))

    def test_manual_instructions_and_ci_do_not_modify_default_association(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 tests/general/finder-open.py --live", readme)
        self.assertIn("osacompile", ci)
        self.assertIn("python3 tests/general/finder-open.py -v", ci)
        self.assertIn("Automation consent", readme)
        self.assertNotIn("osascript", ci)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--live":
        if len(sys.argv) != 3:
            sys.exit("Usage: python3 tests/general/finder-open.py --live /path/to/harmless.pdf")
        try:
            live_finder_open(sys.argv[2])
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            sys.exit(f"Finder Open test failed: {error}")
    else:
        unittest.main()
