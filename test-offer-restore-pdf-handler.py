#!/usr/bin/env python3
"""Regression tests for opt-in PDF default-handler restoration (no macOS changes)."""

import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "offer_pdf_restoration", ROOT / "offer-restore-pdf-handler.py")
offer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(offer)


class PDFDefaultRestorationTests(unittest.TestCase):
    identifier = "/installed/identify-pdf-handler"
    setter = "/source/set-pdf-default-handler.swift"
    app = "/Users/test/Applications/PDF Magic Opener.app"

    def execute(self, current="com.apple.Preview", *, interactive=True,
                response="n", lookup_error=None):
        calls = []
        messages = []

        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            if len(calls) == 1:
                if lookup_error is not None:
                    raise lookup_error
                return subprocess.CompletedProcess(argv, 0, current + "\n", "")
            return subprocess.CompletedProcess(argv, 0, "", "")

        accepted = offer.offer_restore(
            self.identifier, self.setter, self.app, run=run,
            interactive=interactive, ask=lambda question: response, say=messages.append)
        return accepted, calls, messages

    def test_different_handler_requires_explicit_yes(self):
        for response in ("", "n", "no", "maybe", "  "):
            with self.subTest(response=response):
                accepted, calls, messages = self.execute(response=response)
                self.assertFalse(accepted)
                self.assertEqual(len(calls), 1)
                self.assertIn("Keeping the existing", messages[-1])

    def test_acceptance_uses_existing_setter_and_exact_installed_app(self):
        for response in ("y", "YES", " Yes "):
            with self.subTest(response=response):
                accepted, calls, _ = self.execute(response=response)
                self.assertTrue(accepted)
                self.assertEqual(calls[0][0], [self.identifier])
                self.assertEqual(calls[1][0], ["/usr/bin/swift", self.setter, self.app])
                self.assertEqual(calls[1][1], {"check": True, "timeout": 120})

    def test_already_default_never_prompts_or_sets(self):
        accepted, calls, messages = self.execute(current=offer.OPENER_ID, response="yes")
        self.assertFalse(accepted)
        self.assertEqual(len(calls), 1)
        self.assertIn("already the default", messages[-1])

    def test_noninteractive_install_keeps_other_default(self):
        accepted, calls, messages = self.execute(interactive=False, response="yes")
        self.assertFalse(accepted)
        self.assertEqual(len(calls), 1)
        self.assertIn("No changes made", messages[-1])

    def test_bad_or_unverifiable_handler_never_changes_association(self):
        for current in ("", " ", "notabundle", "com.apple.Preview\ncom.adobe.Reader",
                        "com.apple.Preview ", " com.apple.Preview", "other;command"):
            with self.subTest(current=current):
                accepted, calls, messages = self.execute(current=current, response="yes")
                self.assertFalse(accepted)
                self.assertEqual(len(calls), 1)
                self.assertIn("Cannot verify", messages[-1])
        for problem in (FileNotFoundError("no reader"),
                        subprocess.TimeoutExpired("reader", 10),
                        subprocess.CalledProcessError(1, "reader")):
            with self.subTest(problem=type(problem).__name__):
                accepted, calls, messages = self.execute(
                    response="yes", lookup_error=problem)
                self.assertFalse(accepted)
                self.assertEqual(len(calls), 1)
                self.assertIn("Cannot verify", messages[-1])

    def test_installer_uses_offer_without_unconditional_default_change(self):
        installer = (ROOT / "install-allow-and-open.sh").read_text()
        self.assertIn('python3 "$script_dir/offer-restore-pdf-handler.py"', installer)
        self.assertIn('"$install_dir/identify-pdf-handler"', installer)
        self.assertIn('"$script_dir/set-pdf-default-handler.swift" "$app"', installer)
        self.assertNotIn('/usr/bin/swift "$script_dir/set-pdf-default-handler.swift" "$app"', installer)
        self.assertLess(installer.index('lsregister -f "$app"'),
                        installer.index('python3 "$script_dir/offer-restore-pdf-handler.py"'))
        helper = (ROOT / "offer-restore-pdf-handler.py").read_text()
        self.assertNotIn("target-app.txt", helper)
        self.assertNotIn("scan-and-open.py", helper)


if __name__ == "__main__":
    unittest.main()
