#!/usr/bin/env python3
"""Hermetic configuration loading regressions (no installed settings touched)."""

import json
import os
from pathlib import Path
import tempfile
import unittest

from configuration_loader import ConfigurationLoadError, load_configuration

DEFAULTS = {"version": 1, "showScanProgress": True, "browser": "Brave"}


class ConfigurationLoadingTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    self.path = self.root / "config.json"

  def load(self):
    return load_configuration(self.path, defaults=DEFAULTS, version=1)

  def test_missing_file_or_parent_uses_isolated_defaults(self):
    self.assertEqual(self.load(), DEFAULTS)
    self.assertEqual(load_configuration(self.root / "missing" / "config.json",
                                        defaults=DEFAULTS, version=1), DEFAULTS)
    result = self.load()
    result["browser"] = "Changed"
    self.assertEqual(DEFAULTS["browser"], "Brave")
    self.assertFalse(self.path.exists())

  def test_existing_values_preserved_without_write(self):
    data = {"version": 1, "showScanProgress": False,
            "customFeature": {"userChoice": "keep"}}
    self.path.write_text(json.dumps(data))
    before = self.path.read_bytes()
    loaded = self.load()
    self.assertEqual(loaded["showScanProgress"], False)
    self.assertEqual(loaded["browser"], "Brave")
    self.assertEqual(loaded["customFeature"], {"userChoice": "keep"})
    self.assertEqual(self.path.read_bytes(), before)

  def test_rejects_corruption_and_unsupported_versions(self):
    for raw in ('', '[]', '{', '{"version":2}', '{"version":true}',
                '{"version":1,"version":1}', '{"version":1,"x":NaN}'):
      with self.subTest(raw=raw):
        self.path.write_text(raw)
        with self.assertRaises(ConfigurationLoadError):
          self.load()

  def test_rejects_symlinks_and_nonregular_files(self):
    target = self.root / "real.json"
    target.write_text('{"version":1}')
    self.path.symlink_to(target)
    with self.assertRaises(ConfigurationLoadError):
      self.load()
    self.path.unlink()
    self.path.mkdir()
    with self.assertRaises(ConfigurationLoadError):
      self.load()
    self.path.rmdir()
    linked_dir = self.root / "linked"
    linked_dir.symlink_to(self.root, target_is_directory=True)
    with self.assertRaises(ConfigurationLoadError):
      load_configuration(linked_dir / "real.json", defaults=DEFAULTS, version=1)

  def test_rejects_oversize_and_invalid_utf8(self):
    self.path.write_bytes(b" " * 65537)
    with self.assertRaises(ConfigurationLoadError):
      self.load()
    self.path.write_bytes(b"\xff")
    with self.assertRaises(ConfigurationLoadError):
      self.load()

  def test_schema_inputs_must_be_consistent(self):
    for defaults, version in (({}, 1), ({"version": 1}, 2),
                              ({"version": 1}, True)):
      with self.assertRaises(ValueError):
        load_configuration(self.path, defaults=defaults, version=version)


if __name__ == "__main__":
  unittest.main()
