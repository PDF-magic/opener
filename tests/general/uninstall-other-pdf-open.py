#!/usr/bin/env python3
"""Mock-only verification of the post-uninstall PDF viewer test."""

from contextlib import redirect_stderr
import importlib.util
from io import StringIO
from pathlib import Path
import re
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "verify-other-pdf-open.py"
SPEC = importlib.util.spec_from_file_location("verify_other_pdf_open", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class OtherPDFViewerTests(unittest.TestCase):
    def perform(self, *, answer="yes", launch_error=None, platform="darwin",
                interactive=True):
        launched = []
        messages, errors = [], []

        def fake_launch(command, **kwargs):
            launched.append((command, kwargs))
            if launch_error:
                raise launch_error
            pdf = Path(command[1])
            self.assertEqual(command[0], "/usr/bin/open")
            self.assertTrue(pdf.is_file())
            self.assertEqual(pdf.stat().st_mode & 0o777, 0o600)
            self.assertIn("pdf-magic-viewer-check-", str(pdf.parent))
            self.assertIn(b"PDF viewer verification", pdf.read_bytes())
            return subprocess.CompletedProcess(command, 0, b"", b"")

        def ask(question):
            self.assertEqual(question, module.PROMPT)
            if isinstance(answer, BaseException):
                raise answer
            return answer

        outcome = module.verify(platform=platform, interactive=interactive,
                                launch=fake_launch, ask=ask,
                                say=messages.append, error=errors.append)
        for command, _ in launched:
            self.assertFalse(Path(command[1]).exists(), "Test PDF must be removed")
        return outcome, launched, messages, errors

    def test_safe_sample_is_a_well_formed_single_page_pdf(self):
        pdf = module.sample_pdf()
        self.assertTrue(pdf.startswith(b"%PDF-1.4\n"))
        self.assertTrue(pdf.endswith(b"%%EOF\n"))
        xref = int(re.search(rb"startxref\n(\d+)\n", pdf).group(1))
        self.assertEqual(pdf[xref:xref + 4], b"xref")
        offsets = re.findall(rb"(\d{10}) 00000 n", pdf[xref:])
        self.assertEqual(len(offsets), 5)
        for number, offset in enumerate(offsets, start=1):
            self.assertTrue(pdf[int(offset):].startswith(f"{number} 0 obj\n".encode()))
        self.assertIn(b"/Count 1", pdf)

    def test_live_confirmation_only_after_default_open(self):
        code, calls, messages, errors = self.perform()
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], {
            "check": True, "timeout": 20,
            "stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
        })
        self.assertEqual(errors, [])
        self.assertIn("Verified", messages[0])
        self.assertEqual(calls[0][0][0], "/usr/bin/open")
        self.assertNotIn("-a", calls[0][0])
        self.assertNotIn("-b", calls[0][0])

    def test_negative_ambiguous_or_empty_response_fails_closed(self):
        for answer in ("", "no", "maybe", "PDF Magic", " yes please "):
            with self.subTest(answer=answer):
                code, calls, messages, errors = self.perform(answer=answer)
                self.assertEqual(code, 1)
                self.assertEqual(len(calls), 1)
                self.assertFalse(messages)
                self.assertIn("not confirmed", errors[0])

    def test_native_dispatch_failure_is_not_a_success(self):
        for failure in (FileNotFoundError(),
                        subprocess.CalledProcessError(1, "/usr/bin/open"),
                        subprocess.TimeoutExpired("/usr/bin/open", 20)):
            with self.subTest(failure=type(failure).__name__):
                code, calls, messages, errors = self.perform(launch_error=failure)
                self.assertEqual(code, 1)
                self.assertEqual(len(calls), 1)
                self.assertFalse(messages)
                self.assertIn("could not dispatch", errors[0])

    def test_cancellation_or_no_input_never_claims_success(self):
        for answer in (EOFError(), KeyboardInterrupt()):
            code, calls, messages, errors = self.perform(answer=answer)
            self.assertEqual(code, 1)
            self.assertEqual(len(calls), 1)
            self.assertFalse(messages)
            self.assertIn("No viewer confirmation", errors[0])

    def test_non_macos_and_noninteractive_do_not_open_anything(self):
        for platform, interactive in (("linux", True), ("darwin", False)):
            code, calls, messages, errors = self.perform(
                platform=platform, interactive=interactive)
            self.assertEqual(code, 2)
            self.assertFalse(calls)
            self.assertFalse(messages)
            self.assertIn("interactive macOS", errors[0])

    def test_cli_requires_live_and_interactive_terminal(self):
        with redirect_stderr(StringIO()) as err:
            self.assertEqual(module.main([]), 2)
        self.assertIn("--live", err.getvalue())
        with patch.object(module.sys, "platform", "darwin"), \
             patch.object(module.sys.stdin, "isatty", return_value=False), \
             patch.object(module.subprocess, "run") as run, \
             redirect_stderr(StringIO()):
            self.assertEqual(module.main(["--live"]), 2)
        run.assert_not_called()

    def test_documentation_and_required_ci_integration(self):
        guide = (ROOT / "docs/uninstall-procedure.md").read_text(encoding="utf-8")
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 verify-other-pdf-open.py --live", guide)
        self.assertGreater(guide.index("python3 verify-other-pdf-open.py --live"),
                           guide.index("## 7. Verify and retain a recovery path"))
        self.assertIn("PYTHONPATH=. python3 tests/general/uninstall-other-pdf-open.py -v", ci)
        self.assertIn("No uninstall commands or OS mutations run during CI.", guide)


if __name__ == "__main__":
    unittest.main()
