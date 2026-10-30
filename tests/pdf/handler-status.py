#!/usr/bin/env python3
"""Test current macOS PDF-handler status with a mocked read-only helper."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "pdf_handler_status", ROOT / "pdf-handler-status.py")
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)


class PDFHandlerStatusTests(unittest.TestCase):
    def execute(self, value):
        command = [str(status.HANDLER_LOOKUP)]
        completed = subprocess.CompletedProcess(command, 0, value, b"")
        with patch.object(status.subprocess, "run", return_value=completed) as run:
            output, errors = StringIO(), StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                exit_code = status.main([])
        run.assert_called_once_with(
            command, capture_output=True, check=True, timeout=10)
        return exit_code, output.getvalue(), errors.getvalue()

    def test_opener_is_current_default(self):
        code, output, errors = self.execute(b"local.studio.brave-pdf-opener\n")
        self.assertEqual(code, 0)
        self.assertIn("PDF Magic Opener (local.studio.brave-pdf-opener)", output)
        self.assertIn("PDF Magic Opener is the default PDF handler.", output)
        self.assertEqual(errors, "")

    def test_other_pdf_handler_is_not_mistaken_for_the_opener(self):
        for identifier in ("com.apple.Preview", "com.adobe.Reader",
                           "com.google.Chrome"):
            with self.subTest(identifier=identifier):
                code, output, errors = self.execute((identifier + "\n").encode())
                self.assertEqual(code, 0)
                self.assertIn("Current macOS PDF handler: " + identifier, output)
                self.assertIn("PDF Magic Opener is not the default PDF handler.", output)
                self.assertEqual(errors, "")

    def test_unavailable_or_malformed_handler_does_not_show_success(self):
        invalid = (b"", b"\n", b"com.apple.Preview", b"com.apple.Preview\nother\n",
                   b"com.apple.Preview\n\n", b"com..fake\n",
                   b"com.apple.Preview;echo hi\n", b"\xff\n", b"a" * 258 + b"\n")
        for value in invalid:
            with self.subTest(value=value):
                code, output, errors = self.execute(value)
                self.assertEqual(code, 1)
                self.assertEqual(output, "")
                self.assertEqual(errors.strip(), status.LOOKUP_ERROR)

    def test_helper_errors_do_not_fall_back_to_a_guessed_handler(self):
        for error in (FileNotFoundError("missing"),
                      subprocess.CalledProcessError(1, "identify-pdf-handler"),
                      subprocess.TimeoutExpired("identify-pdf-handler", 10)):
            with self.subTest(error=type(error).__name__):
                with patch.object(status.subprocess, "run", side_effect=error):
                    output, errors = StringIO(), StringIO()
                    with redirect_stdout(output), redirect_stderr(errors):
                        code = status.main([])
                self.assertEqual(code, 1)
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(errors.getvalue().strip(), status.LOOKUP_ERROR)

    def test_unsupported_arguments_never_query_the_system(self):
        with patch.object(status.subprocess, "run") as run:
            with redirect_stderr(StringIO()):
                self.assertEqual(status.main(["--change-default"]), 2)
        run.assert_not_called()

    def test_installer_displays_status_after_optional_restoration_offer(self):
        installer = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
        self.assertIn('cp "$script_dir/pdf-handler-status.py" "$install_dir/pdf-handler-status.py"', installer)
        self.assertIn('"$install_dir/identify-pdf-handler"', installer)
        offer = installer.index('python3 "$script_dir/offer-restore-pdf-handler.py"')
        reporter = installer.index('python3 "$install_dir/pdf-handler-status.py"')
        self.assertGreater(reporter, offer)
        self.assertNotIn('/usr/bin/swift "$script_dir/set-pdf-default-handler.swift" "$app"', installer)

    def test_documentation_and_ci_explain_read_only_status(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("only reads", readme)
        self.assertIn("pdf-handler-status.py", readme)
        self.assertIn("identify-pdf-handler", readme)
        self.assertIn("python3 tests/pdf/handler-status.py -v", ci)


if __name__ == "__main__":
    unittest.main()
