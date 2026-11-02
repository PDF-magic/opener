#!/usr/bin/env python3
"""Offline macOS file-handler compatibility-watch regression (opener-1167)."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]

# Existing production call sites, not a second implementation of the launch path.
INVENTORY = {
    "launch-scanned-file.swift": (
        "urlsForApplications(withBundleIdentifier:",
        "urlForApplication(withBundleIdentifier:",
        "open([target], withApplicationAt:",
        "openApplication(at:",
        "urlForApplication(toOpen:",
        "workspace.open(target)",
    ),
    "verify-pdf-target.swift": ("urlsForApplications(toOpen:",),
    "identify-pdf-handler.swift": ("LSCopyDefaultRoleHandlerForContentType(",),
    "set-pdf-default-handler.swift": (
        "LSCopyDefaultRoleHandlerForContentType(",
        "setDefaultApplication(at:",
    ),
    "make-pdf-magic-default.swift": ("setDefaultApplication(",),
    "pdf-handler-history.swift": (
        "LSCopyDefaultRoleHandlerForContentType(",
        "setDefaultApplication(at:",
    ),
}
PROBE_SYMBOLS = (
    "UTType.pdf.identifier",
    "LSCopyDefaultRoleHandlerForContentType(",
    "urlForApplication(withBundleIdentifier:",
    "urlsForApplications(withBundleIdentifier:",
    "urlsForApplications(toOpen:",
    "urlForApplication(toOpen:",
    "setDefaultApplication(at:",
    "open([document], withApplicationAt:",
    "openApplication(at:",
    "workspace.open(document)",
)


def missing_uses(sources):
    return [
        (path, symbol)
        for path, symbols in INVENTORY.items()
        for symbol in symbols
        if symbol not in sources.get(path, "")
    ]


class FileHandlerAPIWatchTests(unittest.TestCase):
    def test_existing_macos_call_sites_remain_in_inventory(self):
        sources = {
            path: (ROOT / path).read_text(encoding="utf-8")
            for path in INVENTORY
        }
        self.assertEqual(missing_uses(sources), [])

    def test_inventory_detects_removed_or_renamed_calls(self):
        fake = {path: "\n".join(symbols) for path, symbols in INVENTORY.items()}
        self.assertEqual(missing_uses(fake), [])
        fake["launch-scanned-file.swift"] = ""
        self.assertIn(
            ("launch-scanned-file.swift", "openApplication(at:"),
            missing_uses(fake),
        )

    def test_probe_typechecks_the_tracked_sdk_surface_without_running_it(self):
        probe = (ROOT / "scripts/macos-file-handler-api-probe.swift").read_text(
            encoding="utf-8"
        )
        self.assertIn("@available(macOS 12.0, *)", probe)
        for symbol in PROBE_SYMBOLS:
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, probe)
        self.assertIn("func verifyFileHandlerSDK(", probe)
        self.assertEqual(probe.count("verifyFileHandlerSDK("), 1)
        self.assertNotIn("CommandLine.arguments", probe)
        self.assertNotIn("ProcessInfo.processInfo.arguments", probe)

    def test_ci_checks_current_sdk_on_pr_main_and_weekly(self):
        workflow = (ROOT / ".github/workflows/macos-file-handler-api-watch.yml").read_text(
            encoding="utf-8"
        )
        for required in (
            "pull_request:", "merge_group:", "push:", "branches: [main]",
            "schedule:", "workflow_dispatch:", "contents: read",
            "runs-on: macos-latest", "xcrun --sdk macosx --show-sdk-version",
            "xcrun swiftc -typecheck -warnings-as-errors",
            "scripts/macos-file-handler-api-probe.swift",
            "tests/general/macos-file-handler-api-watch.py -v",
        ):
            with self.subTest(required=required):
                self.assertIn(required, workflow)
        self.assertNotIn("issues: write", workflow)
        self.assertNotIn("pull-requests: write", workflow)
        self.assertNotIn("set-pdf-default-handler.swift -o", workflow)

    def test_maintenance_runbook_is_linked_and_explicit_about_limits(self):
        index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
        self.assertIn(
            "[macOS file-handler API watch](macos-file-handler-api-watch.md)",
            index,
        )
        content = (ROOT / "docs/macos-file-handler-api-watch.md").read_text(
            encoding="utf-8"
        ).lower()
        for required in (
            "opener-1167", "launch services", "nsworkspace", "uttype",
            "apple", "weekly", "manual", "deprecat", "release notes",
            "not execute", "scanner", "user preferences", "rollback",
        ):
            self.assertIn(required, content)


if __name__ == "__main__":
    unittest.main()
