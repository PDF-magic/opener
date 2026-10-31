#!/usr/bin/env python3
"""Guard the Safari downloaded-file opening regression and CI safety scope."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class SafariDownloadedFileOpenContract(unittest.TestCase):
    def test_real_safari_and_portable_tests_are_required_by_ci(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        source = (ROOT / "tests/browser/safari-download-open.py").read_text(encoding="utf-8")
        self.assertIn("name: Safari downloaded PDF managed opening", ci)
        self.assertIn("sudo /usr/bin/safaridriver --enable", ci)
        self.assertIn("tests/browser/safari-download-open.py --live", ci)
        self.assertIn("tests/browser/safari-download-open.py --self-test", ci)
        self.assertIn("tests/browser/safari-download-open-contract.py -v", ci)
        for required in (
            'GITHUB_ACTIONS") != "true"', "RUNNER_TEMP", 'browserName": "safari"',
            'css selector', '#pdf-download', "/element/", "/click",
            'f"attachment; filename=', "application/pdf", '"127.0.0.1"',
            "ensure_safari_download(pdf, requests)",
            'contents == PDF_BYTES', '"Safari" not in requests[0]["agent"]',
            'os.getxattr(pdf, QUARANTINE_KEY)',
            'os.setxattr(pdf, QUARANTINE_KEY, TEST_TAG)',
            'opener.scan_and_open(str(pdf), "/fixture-clamscan")',
            '("clean", "malware", "scanner-error")',
            'assert events == ["scan"]', "pdf.unlink()",
        ):
            with self.subTest(required=required):
                self.assertIn(required, source)
        self.assertNotIn("unittest.skip", source)
        self.assertNotIn("pytest.skip", source)

    def test_test_does_not_change_runtime_scanner_or_browser_privileges(self):
        source = (ROOT / "tests/browser/safari-download-open.py").read_text(encoding="utf-8")
        for forbidden in (
            "defaults write", "killall Safari", "open -a", "xattr -d",
            "removexattr(", "--load-extension", "sendNativeMessage(",
            "connectNative(", "https://", "file://", "shutil.rmtree(",
            "os.system(", "chmod 777",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertTrue((ROOT / "extensions/webextension/src/background.js")
                        .read_text(encoding="utf-8").strip().endswith("void 0;"))
        assert (ROOT / "scan-and-open.py").is_file()


if __name__ == "__main__":
    unittest.main()
