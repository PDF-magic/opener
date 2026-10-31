#!/usr/bin/env python3
"""Regression tests for the macOS quarantine attribute removal inventory."""

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "quarantine_removal_audit", ROOT / "tools" / "audit_quarantine_removal.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class QuarantineRemovalInventoryTests(unittest.TestCase):
    def test_removal_apis_and_commands_are_identified(self):
        examples = [
            'os.removexattr(document, "com.apple.quarantine")',
            'libc.removexattr(path, "com.apple.quarantine", 0)',
            'fremovexattr(fd, "com.apple.quarantine", 0)',
            'lremovexattr(path, "com.apple.quarantine", 0)',
            '/usr/bin/xattr -d com.apple.quarantine "$file"',
            '/usr/bin/xattr -cr "$app"',
            'subprocess.run(["xattr", "-c", document], check=True)',
            'Process.launchPath = "/usr/bin/xattr"; Process.arguments = ["-d", attr]',
            'url.setResourceValue(nil, forKey: .quarantinePropertiesKey)',
            'LSSetItemAttribute(url, kLSItemQuarantineProperties, nil)',
        ]
        for source in examples:
            with self.subTest(source=source):
                self.assertTrue(audit.suspect_calls(source), source)

    def test_read_only_attribute_lookups_are_not_deletions(self):
        for source in [
            'os.getxattr(path, "com.apple.quarantine")',
            'os.setxattr(path, "com.apple.quarantine", marker)',
            'return None',
            'xattr -p com.apple.quarantine "$document"',
            'xattr -l "$document"',
        ]:
            with self.subTest(source=source):
                self.assertEqual(audit.suspect_calls(source), [])

    def test_only_tracked_runtime_code_is_in_scope(self):
        for path in ["scan-and-open.py", "extensions/webextension/src/background.js",
                     "native-messaging/Host.swift", ".github/workflows/ci.yml"]:
            self.assertTrue(audit.runtime_path(path), path)
        for path in ["tests/general/retain-os-quarantine.py",
                     "test-browser-download-monitoring.swift",
                     "docs/macos-quarantine-removal-inventory.md",
                     "tools/audit_quarantine_removal.py", "secrets/browser-credentials.py",
                     ".env", "user-private-key.pem"]:
            self.assertFalse(audit.runtime_path(path), path)

    def test_legacy_hook_must_remain_noop_with_one_call(self):
        source = ("def remove_quarantine(path):\n"
                  "    '''Leave quarantine intact.'''\n"
                  "    return None\n\n"
                  "def scan_and_open(path):\n"
                  "    remove_quarantine(path)\n")
        self.assertEqual(audit.legacy_hook(source), {
            "definition_line": 1, "call_line": 6, "effect": "none; returns None"
        })
        with self.assertRaises(AssertionError):
            audit.legacy_hook(source.replace(
                "return None", "os.removexattr(path, 'com.apple.quarantine')"))
        with self.assertRaises(AssertionError):
            audit.legacy_hook(source + "remove_quarantine('other')\n")

    def test_new_tracked_runtime_mutator_is_reported(self):
        with tempfile.TemporaryDirectory(prefix="quarantine-audit-test-") as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True,
                           stdout=subprocess.DEVNULL)
            (root / "scan-and-open.py").write_text(
                "def remove_quarantine(path):\n    return None\n\n"
                "def scan_and_open(path):\n    remove_quarantine(path)\n",
                encoding="utf-8")
            worker = root / "native_worker.py"
            worker.write_text("os.getxattr(path, 'com.apple.quarantine')\n",
                              encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add",
                            "scan-and-open.py", "native_worker.py"], check=True,
                           stdout=subprocess.DEVNULL)
            self.assertEqual(audit.inventory(root)["removal_candidates"], [])
            worker.write_text("os.removexattr(path, 'com.apple.quarantine')\n",
                              encoding="utf-8")
            self.assertEqual(audit.inventory(root)["removal_candidates"], [{
                "path": "native_worker.py", "line": 1,
                "kind": "extended-attribute removal API"
            }])

    def test_actual_tracked_runtime_tree_has_no_removers(self):
        report = audit.inventory(ROOT)
        self.assertGreater(report["scanned_runtime_files"], 100)
        self.assertEqual(report["removal_candidates"], [],
                         "Review each removal candidate before merging")
        self.assertEqual(report["legacy_hook"]["path"], "scan-and-open.py")
        self.assertEqual(report["legacy_hook"]["effect"], "none; returns None")


if __name__ == "__main__":
    unittest.main()
