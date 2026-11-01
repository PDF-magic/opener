#!/usr/bin/env python3
"""End-to-end reproducibility and fail-closed regressions (opener-1136)."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
  "release_builder", ROOT / "scripts/build_reproducible_release.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ReproducibleReleaseTests(unittest.TestCase):
  def test_two_isolated_builds_and_checksums(self):
    with tempfile.TemporaryDirectory() as temporary:
      output = Path(temporary) / "out"
      files = builder.build_release(output)
      self.assertEqual(files, sorted(builder.artifact_names(builder.release_version(builder.WEB))))
      lines = []
      for name in files:
        data = (output / name).read_bytes()
        self.assertTrue(data)
        lines.append(hashlib.sha256(data).hexdigest() + "  " + name + "\n")
      self.assertEqual((output / "SHA256SUMS").read_text(encoding="ascii"), "".join(lines))
      self.assertEqual(sorted(x.relative_to(output).as_posix() for x in output.rglob("*")
                              if x.is_file()), ["SHA256SUMS", *files])

  def test_divergent_or_missing_candidate_fails(self):
    with self.assertRaises(builder.BuildError):
      builder.require_identical({"one.zip": b"a"}, {"one.zip": b"b"})
    with self.assertRaises(builder.BuildError):
      builder.require_identical({"one.zip": b"a"}, {})

  def test_existing_output_remains_untouched(self):
    with tempfile.TemporaryDirectory() as temporary:
      output = Path(temporary) / "existing"
      output.mkdir()
      marker = output / "custom"
      marker.write_text("preserve me", encoding="utf-8")
      with self.assertRaises(builder.BuildError):
        builder.build_release(output)
      self.assertEqual(marker.read_text(encoding="utf-8"), "preserve me")

  def test_exact_source_allowlist_never_accesses_credentials_or_fixtures(self):
    self.assertEqual(len(builder.ARCHIVE_FILES), 10)
    self.assertTrue(all("secret" not in p and ".env" not in p and
                        "fixture" not in p and "test" not in p for p in builder.SOURCES))
    policy = (ROOT / "docs/browser-extension-distribution.md").read_text(encoding="utf-8")
    self.assertIn("**Status: NOT RELEASE READY.**", policy)
    self.assertNotIn("**Status: RELEASE READY.**", policy)

  def test_ci_build_is_critical_and_cannot_publish(self):
    workflow = (ROOT / ".github/workflows/reproducible-release-build.yml").read_text(
      encoding="utf-8")
    for trigger in ("pull_request:", "merge_group:", "push:"):
      self.assertIn(trigger, workflow)
    self.assertIn("python3 scripts/build_reproducible_release.py", workflow)
    self.assertIn("python3 tests/general/reproducible-release-build.py -v", workflow)
    self.assertIn("contents: read", workflow)
    self.assertNotIn("contents: write", workflow)
    self.assertNotIn("gh release create", workflow)
    gate = (ROOT / "scripts/require_release_checks.py").read_text(encoding="utf-8")
    self.assertIn('"Reproducible unsigned release candidates",', gate)


if __name__ == "__main__":
  unittest.main()
