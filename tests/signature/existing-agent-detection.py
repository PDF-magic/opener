#!/usr/bin/env python3
"""opener-0937: detect existing updater agents without modifying them."""

import importlib.util
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "signature_update_launchagent", ROOT / "signature_update_launchagent.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ExistingAgentDetectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="signature-agent-detection-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name) / "home"
        self.home.mkdir()
        self.agents = self.home / "Library/LaunchAgents"
        self.plist = self.agents / module.AGENT_FILENAME

    def expected(self):
        return {
            "Label": module.AGENT_LABEL,
            "ProgramArguments": [
                "/bin/bash",
                str(self.home / "Library/Application Support/Studio/allow-and-open/update-malware-signatures.sh"),
            ],
            "RunAtLoad": True,
            "StartInterval": 14400,
        }

    def create_agent(self, properties=None, *, fmt=plistlib.FMT_XML):
        self.agents.mkdir(parents=True, exist_ok=True)
        self.plist.write_bytes(plistlib.dumps(
            self.expected() if properties is None else properties, fmt=fmt
        ))

    def detect(self):
        return module.detect_existing_signature_update_agent(self.home)

    def test_absent_home_structure_does_not_create_any_files(self):
        self.assertFalse(self.detect())
        self.assertFalse((self.home / "Library").exists())
        self.agents.mkdir(parents=True)
        self.assertFalse(self.detect())
        self.assertEqual(list(self.agents.iterdir()), [])

    def test_recognizes_existing_agent_without_touching_custom_settings(self):
        agent = self.expected()
        agent["StartInterval"] = 7200
        agent["StandardOutPath"] = str(self.home / "custom.log")
        self.create_agent(agent)
        before = self.plist.read_bytes()
        before_stat = self.plist.stat()
        self.assertTrue(self.detect())
        self.assertEqual(self.plist.read_bytes(), before)
        self.assertEqual(self.plist.stat().st_mtime_ns, before_stat.st_mtime_ns)
        self.assertEqual(self.plist.stat().st_ino, before_stat.st_ino)

    def test_recognizes_binary_plist(self):
        self.create_agent(fmt=plistlib.FMT_BINARY)
        self.assertTrue(self.detect())

    def test_rejects_wrong_label_and_wrong_program(self):
        for key, value in (
            ("Label", "com.unrelated.agent"),
            ("ProgramArguments", ["/bin/sh", "-c", "echo unsafe"]),
        ):
            with self.subTest(key=key):
                agent = self.expected()
                agent[key] = value
                self.create_agent(agent)
                with self.assertRaises(module.UnrecognizedSignatureUpdateAgent):
                    self.detect()

    def test_rejects_malformed_and_oversized_plist(self):
        self.create_agent()
        for contents in (b"not a plist", b"x" * (module.MAX_PLIST_BYTES + 1)):
            with self.subTest(size=len(contents)):
                self.plist.write_bytes(contents)
                with self.assertRaises(module.UnrecognizedSignatureUpdateAgent):
                    self.detect()

    def test_rejects_linked_or_nonregular_agent_without_following(self):
        self.agents.mkdir(parents=True)
        target = self.home / "unrelated.plist"
        target.write_bytes(plistlib.dumps(self.expected()))
        self.plist.symlink_to(target)
        with self.assertRaises(module.UnrecognizedSignatureUpdateAgent):
            self.detect()
        self.assertEqual(target.read_bytes(), plistlib.dumps(self.expected()))
        self.plist.unlink()
        self.plist.mkdir()
        with self.assertRaises(module.UnrecognizedSignatureUpdateAgent):
            self.detect()
        self.plist.rmdir()
        os.mkfifo(self.plist)
        with self.assertRaises(module.UnrecognizedSignatureUpdateAgent):
            self.detect()

    def test_rejects_symlinked_parent_directory(self):
        outside = self.home / "outside"
        outside.mkdir()
        (self.home / "Library").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(module.UnrecognizedSignatureUpdateAgent):
            self.detect()

    def test_cli_distinguishes_existing_absent_and_conflicting(self):
        env = dict(os.environ, HOME=str(self.home))

        def invoke():
            return subprocess.run(
                [sys.executable, str(ROOT / "signature_update_launchagent.py")],
                env=env, capture_output=True, text=True, timeout=5,
            )

        self.assertEqual((invoke().returncode, invoke().stdout), (0, "absent\n"))
        self.create_agent()
        self.assertEqual((invoke().returncode, invoke().stdout), (0, "existing\n"))
        self.plist.write_text("malformed")
        result = invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def installer_plist_registration(self):
        installer = (ROOT / "install-allow-and-open.sh").read_text()
        match = re.search(
            r"python3 - \"\$app\" \"\$install_dir\" \"\$app_name\" <<'CONFIG'\n(.*?)\nCONFIG",
            installer, re.DOTALL,
        )
        self.assertIsNotNone(match)
        app = self.home / "Test.app"
        (app / "Contents").mkdir(parents=True, exist_ok=True)
        installed = self.home / "Library/Application Support/Studio/allow-and-open"
        return subprocess.run(
            [sys.executable, "-c", match.group(1), str(app), str(installed),
             "PDF Magic Opener"],
            env=dict(os.environ, HOME=str(self.home)),
            capture_output=True, text=True, timeout=5,
        )

    def test_installer_preserves_existing_custom_agent(self):
        agent = self.expected()
        agent["StartInterval"] = 12345
        agent["StandardErrorPath"] = str(self.home / "my-custom-errors.log")
        self.create_agent(agent)
        original = self.plist.read_bytes()
        result = self.installer_plist_registration()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.plist.read_bytes(), original)

    def test_installer_creates_only_absent_agent_and_refuses_clobber(self):
        self.agents.mkdir(parents=True)
        result = self.installer_plist_registration()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(plistlib.loads(self.plist.read_bytes())["Label"], module.AGENT_LABEL)
        self.assertEqual(self.plist.stat().st_mode & 0o777, 0o600)
        before = self.plist.read_bytes()
        duplicate = self.installer_plist_registration()
        self.assertEqual(duplicate.returncode, 0, duplicate.stderr)
        self.assertEqual(self.plist.read_bytes(), before)

    def test_installer_detects_before_writing_and_preserves_existing_plist(self):
        installer = (ROOT / "install-allow-and-open.sh").read_text()
        self.assertIn('agent_state="$(python3 "$script_dir/signature_update_launchagent.py")"', installer)
        self.assertIn('except FileExistsError:', installer)
        self.assertIn('os.O_CREAT | os.O_EXCL', installer)
        self.assertLess(installer.index('agent_state="$(python3'), installer.index("with os.fdopen(fd, 'wb')"))
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("python3 tests/signature/existing-agent-detection.py -v", ci)


if __name__ == "__main__":
    unittest.main()
