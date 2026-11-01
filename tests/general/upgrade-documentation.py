#!/usr/bin/env python3
"""Keep the documented macOS upgrade steps aligned with installer safety."""
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/upgrade-process.md"


class UpgradeDocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guide = DOC.read_text(encoding="utf-8")
        cls.installer = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")

    def test_documented_entry_point_and_prerequisites(self):
        for item in (
            "macOS 13", "complete, trusted", "Allow and Open",
            "xcode-select --install", "bash install-allow-and-open.sh",
            "never with sudo", "not an in-app application",
        ):
            with self.subTest(item=item):
                self.assertIn(item, self.guide)
        self.assertIn("scripts/report_install_prerequisites.py", self.installer)
        self.assertIn('if [ "$EUID" -eq 0 ]; then', self.installer)

    def test_upgrade_does_not_promise_to_replace_security_configuration(self):
        for item in (
            "ClamAV", "INSTALL", "brew install clamav", "not upgraded or",
            "selected PDF browser", "FreshClam", "signature databases",
            "Finder", "default PDF handler", "separate consent",
            "48-hour", "quarantine", "Inline browser PDF",
        ):
            with self.subTest(item=item):
                self.assertIn(item, self.guide)
        self.assertIn("scripts/confirm_clamav_install.py", self.installer)
        self.assertIn("scripts/migrate_update_agent.py", self.installer)
        self.assertIn("scripts/reconcile_update_agent.py", self.installer)
        self.assertIn('os.O_WRONLY | os.O_CREAT | os.O_EXCL', self.installer)
        self.assertIn("scripts/preserve_existing_opener.py", self.installer)

    def test_completion_and_failure_recovery_are_distinct(self):
        for item in (
            "scripts/migration_state.py status", "complete", "partial",
            "pdf-handler-status.py", "Settings → Updates",
            "failed or interrupted", "rollback", "REPAIR",
        ):
            with self.subTest(item=item):
                self.assertIn(item, self.guide)
        self.assertIn('scripts/migration_state.py" --home "$HOME" complete', self.installer)
        self.assertIn("rollback_installation()", self.installer)

    def test_discoverability_and_resolved_local_links(self):
        index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
        self.assertIn("[Upgrade PDF Magic Opener](upgrade-process.md)", index)
        for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", self.guide):
            url = urlsplit(target)
            if not url.scheme and not url.netloc and url.path:
                with self.subTest(target=target):
                    self.assertTrue((DOC.parent / url.path).is_file(), target)

    def test_required_ci_runs_the_regression(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("tests/general/upgrade-documentation.py -v", workflow)
        self.assertIn("python3 scripts/check-docs-layout.py", workflow)


if __name__ == "__main__":
    unittest.main()
