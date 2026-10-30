#!/usr/bin/env python3
"""Verify anonymous origin recording independently from scan-verdict processing."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('scan_origin', (Path(__file__).resolve().parents[2]s[2] / 'record-scan-origin.py'))
origin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(origin)


class RequestOriginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.log = Path(self.temp.name) / 'origin.jsonl'

    def read_log(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_records_each_source_as_independent_boolean_fields(self):
        for source in ('finder', 'browser', 'desktop-application', None, 'invalid'):
            with self.subTest(source=source):
                self.assertTrue(origin.record_origins(source, path=self.log))
        records = self.read_log()
        self.assertEqual(len(records), 5)
        for index, source in enumerate(('finder', 'browser', 'desktop-application', None, 'invalid')):
            record = records[index]
            self.assertEqual({field: record[field] for field in origin.origin_flags(source)},
                             origin.origin_flags(source))
            self.assertIsInstance(record['requested_at'], float)
        self.assertEqual(origin.origin_flags(None), dict.fromkeys(origin.origin_flags(None), False))
        self.assertEqual(origin.origin_flags('invalid'), origin.origin_flags(None))

    def test_one_record_per_request_without_file_paths(self):
        paths = ['/private/user/very private.pdf', '/tmp/other.pdf']
        with patch.object(origin, 'ORIGIN_LOG', self.log), patch.dict(os.environ, {origin.ORIGIN_ENV: 'finder'}):
            self.assertEqual(origin.main(paths), 0)
        self.assertEqual(len(self.read_log()), 2)
        self.assertNotIn('very private.pdf', self.log.read_text())
        self.assertNotIn('/tmp', self.log.read_text())
        self.assertEqual(self.log.stat().st_mode & 0o777, 0o600)

    def test_unknown_source_stays_unclassified(self):
        with patch.object(origin, 'ORIGIN_LOG', self.log), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(origin.main(['/tmp/file.pdf']), 0)
        self.assertTrue(all(value is False for value in origin.origin_flags(None).values()))
        self.assertTrue(all(self.read_log()[0][key] is False for key in origin.origin_flags(None)))

    def test_unsafe_log_target_is_not_followed_or_modified(self):
        target = Path(self.temp.name) / 'other-file'
        target.write_text('keep me safe')
        self.log.symlink_to(target)
        self.assertFalse(origin.record_origins('finder', path=self.log))
        self.assertEqual(target.read_text(), 'keep me safe')

    def test_unwritable_location_does_not_interrupt_request(self):
        blocked = Path(self.temp.name) / 'not-a-folder'
        blocked.write_text('not a folder')
        with patch.object(origin, 'ORIGIN_LOG', blocked / 'origin.jsonl'):
            self.assertEqual(origin.main(['/tmp/file.pdf']), 0)

    def test_empty_request_writes_nothing(self):
        self.assertFalse(origin.record_origins('finder', count=0, path=self.log))
        self.assertFalse(self.log.exists())


if __name__ == '__main__':
    unittest.main()
