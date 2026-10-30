#!/usr/bin/env python3
"""Compile and exercise the PDF handler verification logic without changing macOS associations."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "set-pdf-default-handler.swift"
SWIFT_TEST = ROOT / "test-pdf-default-handler.swift"
ENTRY = 'guard let brave = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.brave.Browser") else {'


class PDFDefaultHandlerVerificationTests(unittest.TestCase):
    def test_registration_is_verified_after_setter_callback(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertEqual(source.count(ENTRY), 1)
        self.assertIn("NSWorkspace.shared.setDefaultApplication(at: handler, toOpen: .pdf)", source)
        self.assertIn("guard pdfDefaultHandlerChangeVerified(application: handler) else {", source)
        callback = source.index("NSWorkspace.shared.setDefaultApplication(at: handler, toOpen: .pdf)")
        verify = source.index("guard pdfDefaultHandlerChangeVerified(application: handler) else {")
        success = source.index('print("PDF opening uses')
        self.assertLess(callback, verify)
        self.assertLess(verify, success)
        self.assertIn("exit(1)", source[verify:success])

        prelude, _, _ = source.partition(ENTRY)
        with tempfile.TemporaryDirectory(prefix="pdf-default-handler-verify-") as folder:
            root = Path(folder)
            harness = root / "verification.swift"
            harness.write_text(prelude + "\n" + SWIFT_TEST.read_text(encoding="utf-8"), encoding="utf-8")
            binary = root / "TestSetPDFHandler"
            compile_result = subprocess.run(
                ["/usr/bin/xcrun", "swiftc", "-parse-as-library", "-warnings-as-errors",
                 str(harness), "-o", str(binary)],
                capture_output=True, text=True,
            )
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            result = subprocess.run(
                [str(binary)], capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PASS: PDF default handler registration", result.stdout)


if __name__ == "__main__":
    unittest.main()
