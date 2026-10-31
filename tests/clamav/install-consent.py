#!/usr/bin/env python3
"""opener-0960: refuse silent package installation and privileged invocation."""

import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts/confirm_clamav_install.py"
spec = importlib.util.spec_from_file_location("confirm_clamav_install", HELPER)
approval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(approval)


class Console:
    """A terminal writes prompts and reads input on separate channels."""

    def __init__(self, response, tty=True):
        self.incoming = io.StringIO(response)
        self.outgoing = io.StringIO()
        self.tty = tty

    def isatty(self):
        return self.tty

    def write(self, message):
        return self.outgoing.write(message)

    def flush(self):
        return self.outgoing.flush()

    def readline(self, limit=-1):
        return self.incoming.readline(limit)

    def getvalue(self):
        return self.outgoing.getvalue()


class InstallationConsentTests(unittest.TestCase):
    def test_literal_interactive_approval_only(self):
        for response, expected in (
            ("INSTALL\n", True),
            ("install\n", False),
            ("yes\n", False),
            ("INSTALL", False),
            ("INSTALL \n", False),
            (" INSTALL\n", False),
            ("INSTALL-more\n", False),
            ("\n", False),
            ("", False),
        ):
            with self.subTest(response=repr(response)):
                self.assertEqual(approval.confirm_installation(Console(response)), expected)

    def test_redirected_input_cannot_authorize(self):
        self.assertFalse(approval.confirm_installation(Console("INSTALL\n", tty=False)))

    def test_no_controlling_terminal_fails_closed(self):
        with patch("builtins.open", side_effect=OSError("no controlling tty")):
            self.assertFalse(approval.confirm_installation())
        with patch("builtins.open", side_effect=OSError), \
                patch.object(sys, "argv", ["confirm_clamav_install.py"]):
            with patch.object(sys, "stderr", io.StringIO()) as diagnostic:
                self.assertEqual(approval.main(), 1)
        self.assertIn("not authorized", diagnostic.getvalue().lower())
        self.assertNotIn("no controlling tty", diagnostic.getvalue())

    def test_explicit_command_and_privilege_disclosure(self):
        output = Console("INSTALL\n")
        self.assertTrue(approval.confirm_installation(output))
        message = output.getvalue()
        self.assertIn("brew install clamav", message)
        self.assertIn("administrator authorization", message)
        self.assertIn("Type INSTALL", message)

    def test_the_confirmation_module_never_executes_commands(self):
        source = HELPER.read_text(encoding="utf-8")
        for forbidden in ("import subprocess", "subprocess.run(", "subprocess.Popen(", "os.system(", "eval(", "shell=True"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_root_rejected_before_all_installer_operations(self):
        source = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
        root_guard = source.index('if [ "$EUID" -eq 0 ]; then')
        self.assertLess(root_guard, source.index('script_dir='))
        self.assertIn("Do not run the PDF Magic Opener installer as root", source)
        self.assertNotIn("sudo ", source.split("\n", 1)[-1].split("script_dir=", 1)[1])

    def test_brew_is_gated_by_existing_binary_check_and_real_consent(self):
        source = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
        start = source.index("if ! [ -x /opt/homebrew/bin/clamscan ]")
        end = source.index("\nfi", start)
        fallback = source[start:end]
        self.assertIn("[ -x /usr/local/bin/clamscan ]", fallback)
        self.assertIn("[ -x /usr/local/clamav/bin/clamscan ]", fallback)
        consent = 'python3 "$script_dir/scripts/confirm_clamav_install.py"'
        self.assertIn(consent, fallback)
        command = 'HOMEBREW_NO_AUTO_UPDATE=1 "$brew_executable" install clamav'
        self.assertIn(command, fallback)
        self.assertIn("scripts/detect_homebrew.py", fallback)
        self.assertLess(fallback.index("scripts/detect_homebrew.py"), fallback.index(consent))
        self.assertLess(fallback.index(consent), fallback.index(command))
        self.assertEqual(source.count(command), 1)
        self.assertNotIn(command, source[:start])

    def test_normal_installer_path_and_scan_gates_remain_present(self):
        installer = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        for anchor in (
            'migration_attempt="$(python3 "$script_dir/scripts/migration_state.py"',
            'python3 "$script_dir/existing_signature_database.py"',
            'python3 "$script_dir/offer-restore-pdf-handler.py"',
        ):
            self.assertIn(anchor, installer)
        self.assertIn("require_supported_scanner_version(scanner)", scanner)
        self.assertIn("check_database()", scanner)
        self.assertIn("remove_quarantine", scanner)
        self.assertIn("tests/clamav/install-consent.py -v",
                      (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
