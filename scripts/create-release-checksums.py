#!/usr/bin/env python3
"""Produce and verify SHA-256 manifests for source-only GitHub release assets."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import sys

TAG = re.compile(r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MANIFEST = "SHA256SUMS"


class ChecksumError(Exception):
  """Release artifact verification failed without publishing anything."""


def asset_names(tag):
  if not TAG.fullmatch(tag):
    raise ChecksumError("Release tag must be canonical stable vMAJOR.MINOR.PATCH")
  prefix = "pdf-magic-opener-" + tag + "-source"
  return tuple(sorted((prefix + ".tar.gz", prefix + ".zip")))


def file_metadata(path, maximum):
  metadata = path.lstat()
  if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= maximum:
    raise ChecksumError("Missing, empty, oversized or unsafe release asset")
  digest = hashlib.sha256()
  with path.open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
      digest.update(chunk)
  if path.lstat().st_ino != metadata.st_ino or path.stat().st_size != metadata.st_size:
    raise ChecksumError("Release asset changed while hashing")
  return metadata.st_size, digest.hexdigest()


def inventory(directory, tag, include_manifest):
  if directory.is_symlink() or not directory.is_dir():
    raise ChecksumError("Expected an isolated release staging directory")
  names = asset_names(tag)
  expected = set(names) | ({MANIFEST} if include_manifest else set())
  if {item.name for item in directory.iterdir()} != expected:
    raise ChecksumError("Release asset inventory differs from the source-only allowlist")
  return {name: file_metadata(directory / name, MAX_ARCHIVE_BYTES)
          for name in names}


def expected_manifest(assets):
  return "".join(digest + "  " + name + "\n"
                 for name, (_, digest) in sorted(assets.items()))


def create_manifest(directory, tag):
  assets = inventory(directory, tag, include_manifest=False)
  try:
    with (directory / MANIFEST).open("x", encoding="ascii", newline="\n") as stream:
      stream.write(expected_manifest(assets))
  except FileExistsError as error:
    raise ChecksumError("Refusing to overwrite an existing checksum manifest") from error
  return verify_manifest(directory, tag)


def verify_manifest(directory, tag):
  assets = inventory(directory, tag, include_manifest=True)
  manifest = directory / MANIFEST
  size, _ = file_metadata(manifest, 4096)
  if size > 4096 or manifest.read_bytes() != expected_manifest(assets).encode("ascii"):
    raise ChecksumError("Checksum manifest is malformed or does not match the release assets")
  return assets


def verify_remote(release_json, directory, tag, assets):
  """Require GitHub's uploaded asset digests to match the verified local bytes."""
  try:
    release = json.loads(release_json.read_text(encoding="utf-8"))
  except (ValueError, OSError) as error:
    raise ChecksumError("Cannot verify GitHub release asset metadata") from error
  if (not isinstance(release, dict) or release.get("draft") is not True
      or release.get("tag_name") != tag):
    raise ChecksumError("Published or unexpected release cannot be modified")
  remote = release.get("assets")
  if not isinstance(remote, list) or not all(isinstance(item, dict) for item in remote):
    raise ChecksumError("GitHub release assets are unavailable")
  expected = {**assets, MANIFEST: file_metadata(directory / MANIFEST, 4096)}
  if len(remote) != len(expected) or {item.get("name") for item in remote} != set(expected):
    raise ChecksumError("Published asset names or count differ from reviewed files")
  for item in remote:
    size, digest = expected[item["name"]]
    if item.get("size") != size or item.get("digest") != "sha256:" + digest:
      raise ChecksumError("GitHub asset size or SHA-256 differs from reviewed bytes")


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--directory", type=Path, required=True)
  parser.add_argument("--tag", required=True)
  parser.add_argument("--verify", action="store_true")
  parser.add_argument("--release-json", type=Path)
  args = parser.parse_args(argv)
  try:
    if args.release_json is not None and not args.verify:
      raise ChecksumError("Remote checks require local verification")
    assets = (verify_manifest(args.directory, args.tag) if args.verify
              else create_manifest(args.directory, args.tag))
    if args.release_json is not None:
      verify_remote(args.release_json, args.directory, args.tag, assets)
  except (OSError, ChecksumError, UnicodeError, ValueError) as error:
    detail = str(error) if isinstance(error, ChecksumError) else "unsafe or invalid release input"
    print("Release checksums blocked: " + detail, file=sys.stderr)
    return 1
  print("Verified SHA256SUMS and exact source-only release asset inventory.")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
