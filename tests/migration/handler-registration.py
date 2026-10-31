#!/usr/bin/env python3
"""Hermetic migration tests: never change Launch Services on the CI machine."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts/reconcile_pdf_handler_registration.py"
spec = importlib.util.spec_from_file_location("pdf_registration", SOURCE)
registration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registration)


class PDFHandlerRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pdf-handler-reg-")
        self.addCleanup(self.temp.cleanup)
        apps = Path(self.temp.name) / "Applications"
        apps.mkdir()
        self.installed = apps / "PDF Magic Opener.app"
        self.installed.mkdir()
        self.legacy = apps / "Open PDFs in Brave.app"
        self.calls = []

    def reconcile(self, before, after=None, *, fail=None):
        inventories = iter([before, [str(self.installed)] if after is None else after])

        def lookup():
            return next(inventories)

        def run(args, **kwargs):
            self.calls.append((args, kwargs))
            if fail == args[1]:
                raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(args, 0)

        registration.reconcile(self.installed, self.legacy, lookup=lookup, run=run)

    def test_fresh_install_registers_one_handler_without_touching_defaults(self):
        self.reconcile([])
        self.assertEqual(self.calls, [
            ([registration.LSREGISTER, "-f", str(self.installed)],
             {"check": True, "timeout": 30})
        ])

    def test_upgrade_withdraws_only_absent_legacy_registration(self):
        self.reconcile([str(self.legacy)])
        self.assertEqual([call[0][1] for call in self.calls], ["-f", "-u"])
        self.assertEqual(self.calls[1][0][-1], str(self.legacy))
        self.assertTrue(self.installed.is_dir())

    def test_repeated_install_does_not_unregister_working_app(self):
        self.reconcile([str(self.installed)])
        self.assertEqual(len(self.calls), 1)

    def test_unknown_live_or_stale_registration_blocks_before_side_effects(self):
        foreign = self.installed.parent / "Another Opener.app"
        foreign.mkdir()
        for path in (str(foreign), "/Applications/PDF Magic Opener.app",
                     "/missing/Old Opener.app"):
            with self.subTest(path=path):
                self.calls.clear()
                with self.assertRaises(registration.RegistrationConflict):
                    self.reconcile([path])
                self.assertEqual(self.calls, [])

    def test_live_legacy_bundle_blocks_migration(self):
        self.legacy.mkdir()
        with self.assertRaises(registration.RegistrationConflict):
            self.reconcile([str(self.legacy)])
        self.assertEqual(self.calls, [])
        self.assertTrue(self.legacy.is_dir())

    def test_symlinked_legacy_alias_is_not_withdrawn(self):
        self.legacy.symlink_to(self.installed.parent / "missing", target_is_directory=True)
        with self.assertRaises(registration.RegistrationConflict):
            self.reconcile([str(self.legacy)])
        self.assertEqual(self.calls, [])

    def test_invalid_inventory_fails_before_registering(self):
        for entries in (None, {}, ["relative.app"], [str(self.installed)] * 2,
                        [123], [str(self.installed) + "/../other.app"]):
            with self.subTest(entries=entries):
                self.calls.clear()
                with self.assertRaises(registration.RegistrationConflict):
                    self.reconcile(entries)
                self.assertEqual(self.calls, [])

    def test_failed_registration_does_not_withdraw_legacy(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.reconcile([str(self.legacy)], fail="-f")
        self.assertEqual([call[0][1] for call in self.calls], ["-f"])

    def test_unregistration_error_is_not_silently_ignored(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.reconcile([str(self.legacy)], fail="-u")
        self.assertEqual([call[0][1] for call in self.calls], ["-f", "-u"])

    def test_requires_exactly_one_current_registration_after_migration(self):
        for after in ([], [str(self.installed), str(self.legacy)]):
            self.calls.clear()
            with self.assertRaises(registration.RegistrationConflict):
                self.reconcile([str(self.legacy)], after=after)
            self.assertEqual([call[0][1] for call in self.calls], ["-f", "-u"])

    def test_refuses_missing_and_symlinked_current_app(self):
        self.installed.rmdir()
        with self.assertRaises(registration.RegistrationConflict):
            self.reconcile([])
        self.installed.symlink_to(self.installed.parent / "missing", target_is_directory=True)
        with self.assertRaises(registration.RegistrationConflict):
            self.reconcile([])
        self.assertEqual(self.calls, [])

    def test_installer_integrates_after_bundle_verification_and_before_prompt(self):
        source = (ROOT / "install-allow-and-open.sh").read_text()
        self.assertIn('scripts/reconcile_pdf_handler_registration.py', source)
        self.assertIn('scripts/list_registered_pdf_openers.swift', source)
        self.assertNotIn('lsregister -f "$app"', source)
        self.assertLess(source.index('scripts/verify_pdf_opener_bundle.py'),
                        source.index('mv "$app" "$installed_app"'))
        self.assertLess(source.index('mv "$app" "$installed_app"'),
                        source.index('scripts/reconcile_pdf_handler_registration.py'))
        self.assertLess(source.index('scripts/reconcile_pdf_handler_registration.py'),
                        source.index('offer-restore-pdf-handler.py'))
        helper = SOURCE.read_text()
        self.assertNotIn("setDefaultApplication", helper)
        self.assertNotIn("target-app.txt", helper)
        self.assertNotIn('"-kill"', helper)
        self.assertIn('withBundleIdentifier: "local.studio.brave-pdf-opener"',
                      (ROOT / "scripts/list_registered_pdf_openers.swift").read_text())

    def test_lookup_decodes_fixed_enumerator_and_rejects_bad_json(self):
        enumerator = Path("/trusted/list.swift")
        with patch.object(registration.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0,
                                                                   '["/tmp/known.app"]', "")) as run:
            self.assertEqual(registration.registered_paths(enumerator), ["/tmp/known.app"])
            run.assert_called_once_with(["/usr/bin/swift", str(enumerator)],
                                        check=True, timeout=60,
                                        capture_output=True, text=True)
        with patch.object(registration.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, "not json", "")):
            with self.assertRaises(registration.RegistrationConflict):
                registration.registered_paths(enumerator)


if __name__ == "__main__":
    unittest.main()
