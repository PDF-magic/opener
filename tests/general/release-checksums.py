#!/usr/bin/env python3
"""Source-only release checksum publication regressions (opener-1156)."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
  "release_checksums", ROOT / "scripts/create_release_checksums.py")
checksums = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checksums)
TAG = "v0.1.0"


class ReleaseChecksumTests(unittest.TestCase):
  def setUp(self):
    temporary = tempfile.TemporaryDirectory()
    self.addCleanup(temporary.cleanup)
    self.directory = Path(temporary.name) / "release"
    self.directory.mkdir()
    for index, name in enumerate(checksums.asset_names(TAG)):
      (self.directory / name).write_bytes(b"synthetic source archive " + bytes([index]))
    self.assets = checksums.create_manifest(self.directory, TAG)

  def test_deterministic_manifest_covers_both_downloadable_source_assets(self):
    manifest = (self.directory / "SHA256SUMS").read_text(encoding="ascii")
    expected = "".join(hashlib.sha256((self.directory / name).read_bytes()).hexdigest()
                       + "  " + name + "\n" for name in checksums.asset_names(TAG))
    self.assertEqual(manifest, expected)
    self.assertEqual(checksums.verify_manifest(self.directory, TAG), self.assets)
    self.assertEqual(checksums.main(["--directory", str(self.directory),
                                    "--tag", TAG, "--verify"]), 0)

  def test_rejects_tampering_and_malformed_manifest(self):
    name = checksums.asset_names(TAG)[0]
    path = self.directory / name
    path.write_bytes(b"modified source download")
    with self.assertRaises(checksums.ChecksumError):
      checksums.verify_manifest(self.directory, TAG)
    path.write_bytes(b"synthetic source archive " + bytes([0]))
    manifest = self.directory / "SHA256SUMS"
    for malformed in ("", manifest.read_text(encoding="ascii") * 2,
                      "0" * 64 + "  ../escape.zip\n",
                      manifest.read_text(encoding="ascii").upper()):
      with self.subTest(malformed=malformed[:30]):
        manifest.write_text(malformed, encoding="ascii")
        with self.assertRaises(checksums.ChecksumError):
          checksums.verify_manifest(self.directory, TAG)

  def test_rejects_missing_extra_symlinks_and_invalid_tags(self):
    for tag in ("v1.2.3-rc.1", "v01.2.3", "../v1.0.0"):
      with self.assertRaises(checksums.ChecksumError):
        checksums.asset_names(tag)
    name = checksums.asset_names(TAG)[0]
    path = self.directory / name
    path.unlink()
    with self.assertRaises(checksums.ChecksumError):
      checksums.verify_manifest(self.directory, TAG)
    path.symlink_to(self.directory / checksums.asset_names(TAG)[1])
    with self.assertRaises(checksums.ChecksumError):
      checksums.verify_manifest(self.directory, TAG)
    path.unlink()
    path.write_bytes(b"synthetic source archive " + bytes([0]))
    (self.directory / "extra.zip").write_bytes(b"unreviewed")
    with self.assertRaises(checksums.ChecksumError):
      checksums.verify_manifest(self.directory, TAG)
    (self.directory / "extra.zip").unlink()
    with self.assertRaises(checksums.ChecksumError):
      checksums.create_manifest(self.directory, TAG)

  def test_rejects_empty_source_and_symlink_manifest(self):
    name = checksums.asset_names(TAG)[0]
    (self.directory / name).write_bytes(b"")
    with self.assertRaises(checksums.ChecksumError):
      checksums.verify_manifest(self.directory, TAG)
    (self.directory / name).write_bytes(b"synthetic source archive " + bytes([0]))
    (self.directory / "SHA256SUMS").unlink()
    (self.directory / "SHA256SUMS").symlink_to(self.directory / name)
    with self.assertRaises(checksums.ChecksumError):
      checksums.verify_manifest(self.directory, TAG)

  def test_remote_digests_must_match_before_making_draft_public(self):
    items = []
    for name, (size, digest) in {
      **self.assets,
      "SHA256SUMS": checksums.file_metadata(self.directory / "SHA256SUMS", 4096),
    }.items():
      items.append({"name": name, "size": size, "digest": "sha256:" + digest})
    release = {"draft": True, "tag_name": TAG, "assets": items}
    metadata = self.directory.parent / "github-release.json"
    def verify(payload):
      metadata.write_text(json.dumps(payload), encoding="utf-8")
      checksums.verify_remote(metadata, self.directory, TAG, self.assets)
    verify(release)
    for invalid in (
      {**release, "draft": False},
      {**release, "tag_name": "v9.9.9"},
      {**release, "assets": items[:-1]},
      {**release, "assets": items + [items[0]]},
      {**release, "assets": [{**items[0], "digest": "sha256:" + "0"*64}, *items[1:]]},
      {**release, "assets": [{**items[0], "size": 0}, *items[1:]]},
      {**release, "assets": [{**items[0], "digest": None}, *items[1:]]},
    ):
      with self.subTest(invalid=invalid), self.assertRaises(checksums.ChecksumError):
        verify(invalid)

  def test_guarded_workflow_publishes_only_verified_sources(self):
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    regression = (ROOT / ".github/workflows/release-gate-tests.yml").read_text(
      encoding="utf-8")
    gate = (ROOT / "scripts/require_release_checks.py").read_text(encoding="utf-8")
    audit = (ROOT / "docs/browser-extension-distribution.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs/release-gate.md").read_text(encoding="utf-8")
    for phrase in ("git archive --format=tar", "git archive --format=zip",
                   "gzip -n", "SHA256SUMS", "gh release create", "--draft",
                   "gh release upload", "gh release edit", "--draft=false",
                   "--release-json", "--verify-tag"):
      self.assertIn(phrase, workflow)
    self.assertLess(workflow.index("gh release create"), workflow.index("gh release upload"))
    self.assertLess(workflow.index("gh release upload"), workflow.index("--release-json"))
    self.assertLess(workflow.index("--release-json"), workflow.index("gh release edit"))
    self.assertEqual(workflow.count("python3 scripts/require_release_checks.py --tag"), 2)
    self.assertNotIn("--clobber", workflow)
    self.assertNotIn("pdf-magic-opener-macos-unsigned.zip", workflow)
    self.assertNotIn("unsigned-release-candidates", workflow)
    self.assertIn("tests/general/release-checksums.py -v", regression)
    self.assertIn('"Release gating regression suite",', gate)
    self.assertIn("**Status: NOT RELEASE READY.**", audit)
    self.assertIn("source-only", guide)
    self.assertIn("shasum -a 256 -c SHA256SUMS", guide)


if __name__ == "__main__":
  unittest.main()
