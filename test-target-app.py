#!/usr/bin/env python3
"""Verify configurable PDF destination without relaxing the scan gate."""
import importlib.util
import sqlite3
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import file_launcher as launcher

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('scan_and_open_target', ROOT / 'scan-and-open.py')
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)

INSTALLER = (ROOT / 'install-allow-and-open.sh').read_text()
MARKER = "python3 - \"$install_dir/target-app.txt\" <<'TARGET_APP'\n"
assert INSTALLER.count(MARKER) == 1
INIT = INSTALLER.split(MARKER, 1)[1].split('\nTARGET_APP\n', 1)[0]


class TargetApplicationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.config = root / 'target-app.txt'
        self.document = root / 'selected.PDF'
        self.document.write_bytes(b'%PDF-1.4\nTest document')
        target_setting = patch.object(launcher, 'TARGET_APP_CONFIG', self.config)
        target_setting.start()
        self.addCleanup(target_setting.stop)
        cache_setting = patch.object(opener, 'CACHE_DB', root / 'clean-cache.sqlite3')
        cache_setting.start()
        self.addCleanup(cache_setting.stop)
        audit_setting = patch.object(opener, 'SCAN_REQUEST_DB', root / 'request-log.sqlite3')
        audit_setting.start()
        self.addCleanup(audit_setting.stop)

    def scan_clean(self, item=None):
        complete = subprocess.CompletedProcess([], 0, 'file: OK', '')
        with patch.object(opener.subprocess, 'run', return_value=complete) as run, \
                patch.object(opener, 'remove_quarantine') as quarantine:
            opener.scan_and_open(str(item or self.document), '/scanner')
        return run, quarantine

    def test_missing_configuration_keeps_brave_default(self):
        self.assertEqual(launcher.pdf_target_application(), 'com.brave.Browser')
        run, quarantine = self.scan_clean()
        self.assertEqual(run.call_args.args[0], [str(launcher.NATIVE_LAUNCHER), '--bundle-id', 'com.brave.Browser',
                                                  str(self.document)])
        quarantine.assert_called_once()

    def test_configured_bundle_identifier_used_only_after_clean_scan(self):
        self.config.write_text('com.apple.Preview\n')
        run, quarantine = self.scan_clean()
        self.assertEqual(run.call_args.args[0], [str(launcher.NATIVE_LAUNCHER), '--bundle-id', 'com.apple.Preview',
                                                  str(self.document)])
        self.assertEqual(run.call_args_list[0].args[0][0], '/scanner')
        self.assertIn('--alert-encrypted=yes', run.call_args_list[0].args[0])
        with sqlite3.connect(opener.SCAN_REQUEST_DB) as db:
            actual = db.execute('SELECT intended_destination_application FROM scan_requests').fetchone()
        self.assertEqual(actual, ('com.apple.Preview',))
        quarantine.assert_called_once()

    def test_google_chrome_launches_only_after_clean_scan_and_pdf_preflight(self):
        self.config.write_text('com.google.Chrome\n')
        run, quarantine = self.scan_clean()
        commands = [call.args[0] for call in run.call_args_list]
        preflight = [str(launcher.PDF_TARGET_VERIFIER), 'com.google.Chrome']
        launch = [str(launcher.NATIVE_LAUNCHER), '--bundle-id',
                  'com.google.Chrome', str(self.document)]
        self.assertEqual(commands[0][0], '/scanner')
        self.assertIn('--alert-encrypted=yes', commands[0])
        self.assertIn(preflight, commands)
        self.assertEqual(commands[-1], launch)
        self.assertLess(commands.index(preflight), commands.index(launch))
        with sqlite3.connect(opener.SCAN_REQUEST_DB) as db:
            destination = db.execute(
                'SELECT intended_destination_application FROM scan_requests'
            ).fetchone()
        self.assertEqual(destination, ('com.google.Chrome',))
        quarantine.assert_called_once()

    def test_google_chrome_unregistered_pdf_handler_blocks_launch(self):
        self.config.write_text('com.google.Chrome\n')
        def execute(command, *args, **kwargs):
            if command[0] == str(launcher.PDF_TARGET_VERIFIER):
                return subprocess.CompletedProcess(command, 1, '', 'unsupported')
            return subprocess.CompletedProcess(command, 0, 'file: OK', '')
        with patch.object(opener.subprocess, 'run', side_effect=execute) as run, \
                patch.object(opener, 'remove_quarantine') as quarantine:
            with self.assertRaisesRegex(RuntimeError, 'opening was stopped'):
                opener.scan_and_open(str(self.document), '/scanner')
        self.assertTrue(any(call.args[0][0] == str(launcher.PDF_TARGET_VERIFIER)
                            for call in run.call_args_list))
        self.assertFalse(any(call.args[0][0] == str(launcher.NATIVE_LAUNCHER)
                             for call in run.call_args_list))
        quarantine.assert_not_called()

    def test_preflight_and_launch_keep_original_target_if_preference_changes(self):
        self.config.write_text('com.apple.Preview\n')
        seen = []

        def change_preference(path, target_app=None):
            seen.append((path, target_app))
            self.config.write_text('com.brave.Browser\n')

        with patch.object(opener, 'verify_launch_target',
                          side_effect=change_preference):
            run, quarantine = self.scan_clean()
        self.assertEqual(seen, [(self.document, 'com.apple.Preview')])
        self.assertEqual(
            run.call_args.args[0],
            [str(launcher.NATIVE_LAUNCHER), '--bundle-id',
             'com.apple.Preview', str(self.document)],
        )
        quarantine.assert_called_once()

    def test_invalid_settings_fail_before_scan_or_quarantine_changes(self):
        for content in ('', 'Preview', '--evil', 'com.apple.Preview\nother',
                        'com..bad', 'local.studio.brave-pdf-opener', 'x' * 260):
            with self.subTest(value=content[:30]):
                self.config.write_text(content)
                with patch.object(opener.subprocess, 'run') as run, \
                        patch.object(opener, 'remove_quarantine') as quarantine:
                    with self.assertRaises(RuntimeError):
                        opener.scan_and_open(str(self.document), '/scanner')
                run.assert_not_called()
                quarantine.assert_not_called()

    def test_symlink_and_nonregular_configuration_are_blocked(self):
        original = self.config.with_name('safe-other')
        original.write_text('com.apple.Preview\n')
        self.config.symlink_to(original)
        with self.assertRaises(RuntimeError):
            launcher.pdf_target_application()
        self.config.unlink()
        self.config.mkdir()
        with self.assertRaises(RuntimeError):
            launcher.pdf_target_application()

    def test_malware_never_opens_configured_application(self):
        self.config.write_text('com.apple.Preview\n')
        detected = subprocess.CompletedProcess([], 1, 'file: Malware FOUND', '')
        with patch.object(opener.subprocess, 'run', return_value=detected) as run, \
                patch.object(opener, 'remove_quarantine') as quarantine:
            with self.assertRaisesRegex(RuntimeError, 'Malware'):
                opener.scan_and_open(str(self.document), '/scanner')
        self.assertEqual(run.call_count, 1)
        quarantine.assert_not_called()

    def test_non_pdf_uses_system_default_regardless_of_setting(self):
        other = self.config.with_name('notes.txt')
        other.write_bytes(b'notes')
        self.config.write_text('not a bundle ID')
        run, quarantine = self.scan_clean(other)
        self.assertEqual(run.call_args.args[0], [str(launcher.NATIVE_LAUNCHER), str(other)])
        quarantine.assert_called_once()

    def test_installer_creates_private_default_and_preserves_custom_choice(self):
        for value in ('com.brave.Browser', 'com.apple.Preview'):
            result = subprocess.run([sys.executable, '-', str(self.config)], input=INIT,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.config.read_text(), value + '\n')
            self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
            self.config.write_text('com.apple.Preview\n')

    def test_installer_never_follows_existing_symlink(self):
        original = self.config.with_name('untouched.txt')
        original.write_text('do not overwrite')
        self.config.symlink_to(original)
        result = subprocess.run([sys.executable, '-', str(self.config)], input=INIT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(original.read_text(), 'do not overwrite')


if __name__ == '__main__':
    unittest.main()
