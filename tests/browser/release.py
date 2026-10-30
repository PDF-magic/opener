#!/usr/bin/env python3
"""Regression tests for macOS stable/preview browser release identification."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import plistlib
import tempfile
import unittest

from browser_release import identify_release, inspect_app_bundle, main


class BrowserReleaseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def make_app(self, name, identifier, **values):
        app = self.root / (name + ".app")
        contents = app / "Contents"
        contents.mkdir(parents=True)
        with (contents / "Info.plist").open("wb") as stream:
            plistlib.dump({"CFBundleIdentifier": identifier,
                           "CFBundleShortVersionString": "125.0.1",
                           **values}, stream)
        return app

    def test_standard_and_preview_identifiers_are_distinct(self):
        releases = {
            "com.brave.Browser": ("Brave", "stable", "stable"),
            "com.brave.Browser.beta": ("Brave", "beta", "preview"),
            "com.brave.Browser.nightly": ("Brave", "nightly", "preview"),
            "com.google.Chrome.beta": ("Google Chrome", "beta", "preview"),
            "com.google.Chrome.dev": ("Google Chrome", "dev", "preview"),
            "com.google.Chrome.canary": ("Google Chrome", "canary", "preview"),
            "org.mozilla.firefox": ("Mozilla Firefox", "stable", "stable"),
            "org.mozilla.firefoxdeveloperedition": ("Mozilla Firefox", "developer", "preview"),
            "org.mozilla.nightly": ("Mozilla Firefox", "nightly", "preview"),
            "com.microsoft.edgemac": ("Microsoft Edge", "stable", "stable"),
            "com.microsoft.edgemac.Beta": ("Microsoft Edge", "beta", "preview"),
            "com.microsoft.edgemac.Dev": ("Microsoft Edge", "dev", "preview"),
            "com.microsoft.edgemac.Canary": ("Microsoft Edge", "canary", "preview"),
            "com.apple.Safari": ("Safari", "stable", "stable"),
            "com.apple.SafariTechnologyPreview": ("Safari", "technology-preview", "preview"),
            "com.vivaldi.Vivaldi": ("Vivaldi", "stable", "stable"),
            "com.vivaldi.Vivaldi.snapshot": ("Vivaldi", "snapshot", "preview"),
            "com.operasoftware.Opera": ("Opera", "stable", "stable"),
            "org.chromium.Chromium": ("Chromium", "stable", "stable"),
            "company.thebrowser.Browser": ("Arc", "stable", "stable"),
        }
        for identifier, expected in releases.items():
            with self.subTest(identifier=identifier):
                release = identify_release({"CFBundleIdentifier": identifier})
                self.assertEqual((release.family, release.channel, release.kind), expected)

    def test_chrome_shared_bundle_id_checks_keystone_channel(self):
        for channel, expected in (
            (None, ("stable", "stable")),
            ("", ("stable", "stable")),
            ("beta", ("beta", "preview")),
            ("dev", ("dev", "preview")),
            ("canary", ("canary", "preview")),
            ("unrecognized", ("unknown", "unknown")),
        ):
            with self.subTest(channel=channel):
                info = {"CFBundleIdentifier": "com.google.Chrome",
                        "KSProductID": "com.google.Chrome"}
                if channel is not None:
                    info["KSChannelID"] = channel
                result = identify_release(info)
                self.assertEqual((result.channel, result.kind), expected)
        result = identify_release({"CFBundleIdentifier": "com.google.Chrome"})
        self.assertEqual((result.channel, result.kind), ("unknown", "unknown"))

    def test_unknown_and_similarly_named_bundles_are_not_misclassified(self):
        for bundle_id in ("com.google.Chrome.beta.malicious",
                          "com.brave.Browser.beta.extra", "org.mozilla.firefoxalpha",
                          "com.microsoft.edgemac.beta", "com.fake.Browser",
                          "com.google.chrome.for.testing"):
            with self.subTest(bundle_id=bundle_id):
                release = identify_release({"CFBundleIdentifier": bundle_id})
                self.assertEqual((release.family, release.kind), (None, "unknown"))
        self.assertEqual(identify_release({"CFBundleName": "Firefox Nightly"}).kind, "unknown")

    def test_installed_app_metadata_and_version_are_read_only(self):
        app = self.make_app("Beta", "com.brave.Browser.beta")
        before = (app / "Contents" / "Info.plist").read_bytes()
        result = inspect_app_bundle(app)
        self.assertEqual((result.bundle_id, result.channel, result.kind, result.version),
                         ("com.brave.Browser.beta", "beta", "preview", "125.0.1"))
        self.assertEqual((app / "Contents" / "Info.plist").read_bytes(), before)
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([str(app)]), 0)
        self.assertEqual(json.loads(output.getvalue())["kind"], "preview")

    def test_rejects_bad_plists_and_symlinks(self):
        app = self.make_app("Stable", "org.mozilla.firefox")
        metadata = app / "Contents" / "Info.plist"
        metadata.write_text("invalid plist")
        with self.assertRaises(ValueError):
            inspect_app_bundle(app)
        metadata.unlink()
        outside = self.root / "other.plist"
        with outside.open("wb") as stream:
            plistlib.dump({"CFBundleIdentifier": "org.mozilla.firefox"}, stream)
        metadata.symlink_to(outside)
        with self.assertRaises(ValueError):
            inspect_app_bundle(app)
        linked_app = self.root / "Linked.app"
        linked_app.symlink_to(app, target_is_directory=True)
        with self.assertRaises(ValueError):
            inspect_app_bundle(linked_app)
        with self.assertRaises(ValueError):
            inspect_app_bundle(self.root)

    def test_no_guess_from_version_or_display_name(self):
        app = self.make_app("Canary", "org.example.unknown",
                            CFBundleName="Google Chrome Canary",
                            CFBundleShortVersionString="125.0.1-canary")
        release = inspect_app_bundle(app)
        self.assertEqual((release.family, release.channel, release.kind),
                         (None, "unknown", "unknown"))
        self.assertEqual(release.version, "125.0.1-canary")

    def test_invalid_application_returns_path_free_diagnostic(self):
        err = StringIO()
        with redirect_stderr(err):
            self.assertEqual(main([str(self.root / "private.app")]), 1)
        self.assertNotIn(str(self.root), err.getvalue())


if __name__ == "__main__":
    unittest.main()
