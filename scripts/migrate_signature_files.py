#!/usr/bin/env python3
"""Safely transfer compatible on-disk ClamAV signatures (opener-0941).

This is an explicit migration operation, not source discovery or scan approval.
Only a trusted installation orchestrator should supply the legacy directory,
destination, and installed ClamAV executable. No freshness stamp is migrated.
"""

import argparse
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

DATABASES = ("main", "daily", "bytecode")
EXTENSIONS = ("cvd", "cld")
CUSTOM_EXTENSIONS = frozenset({
  ".ndb", ".hdb", ".hsb", ".ldb", ".mdb", ".idb",
  ".fp", ".ign2", ".yar", ".yara",
})
MAX_FILE_BYTES = 512 * 1024 * 1024
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class MigrationError(Exception):
  """A source cannot safely be reused; installed files stay untouched."""


def _safe_directory(path):
  for part in (path, *path.parents):
    if part.is_symlink():
      raise MigrationError("Signature migration path contains a link")
  if not path.is_dir():
    raise MigrationError("Signature migration directory is unavailable")


def _regular_file(path, *, database):
  try:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
  except OSError as error:
    raise MigrationError("Signature source is unavailable or unsafe") from error
  try:
    before = os.fstat(descriptor)
    if (not stat.S_ISREG(before.st_mode) or before.st_size == 0
        or before.st_size > MAX_FILE_BYTES):
      raise MigrationError("Signature source is not a usable regular file")
    with os.fdopen(os.dup(descriptor), "rb") as stream:
      header = stream.read(512 if database else 1)
    if database and (before.st_size < 512 or not header.startswith(b"ClamAV-VDB:")):
      raise MigrationError("Unsupported ClamAV signature database format")
    return descriptor, before
  except BaseException:
    os.close(descriptor)
    raise


def _files_to_migrate(source):
  files = []
  for database in DATABASES:
    variants = [
      source / (database + "." + extension)
      for extension in EXTENSIONS
      if os.path.lexists(source / (database + "." + extension))
    ]
    if len(variants) != (0 if database == "bytecode" and not variants else 1):
      raise MigrationError("Missing or ambiguous ClamAV signature database")
    files.extend((path, True) for path in variants)
  for path in source.iterdir():
    if (path.name not in {candidate.name for candidate, _ in files}
        and SAFE_NAME.fullmatch(path.name)
        and path.suffix.lower() in CUSTOM_EXTENSIONS):
      files.append((path, False))
  return files


def migrate_signatures(source, destination, scanner):
  """Return True only after one verified, atomic, non-overwriting migration.

  Existing destination directories always win, even when empty. The source
  and user-managed files remain untouched. No success/update marker is copied.
  """
  source, destination, scanner = Path(source), Path(destination), Path(scanner)
  _safe_directory(source)
  _safe_directory(destination.parent)
  if source == destination or destination in source.parents or source in destination.parents:
    raise MigrationError("Source and destination must be separate directories")
  if os.path.lexists(destination):
    return False
  if not scanner.is_file() or not os.access(scanner, os.X_OK):
    raise MigrationError("Compatible ClamAV scanner is unavailable")

  files = _files_to_migrate(source)
  with tempfile.TemporaryDirectory(prefix=".signature-migration.", dir=destination.parent) as temporary:
    staged = Path(temporary) / "verified"
    staged.mkdir(mode=0o700)
    for path, database in files:
      descriptor, before = _regular_file(path, database=database)
      try:
        target = staged / path.name
        with os.fdopen(os.dup(descriptor), "rb") as stream, target.open("xb") as output:
          shutil.copyfileobj(stream, output, 1024 * 1024)
        target.chmod(0o600)
        after = os.fstat(descriptor)
        if (before.st_size != after.st_size or before.st_ino != after.st_ino
            or before.st_mtime_ns != after.st_mtime_ns):
          raise MigrationError("Signature source changed during migration")
      finally:
        os.close(descriptor)

    probe = Path(temporary) / "compatibility-probe"
    probe.write_bytes(b"PDF Magic signature migration test\n")
    try:
      result = subprocess.run(
        [str(scanner), "--database=" + str(staged), "--no-summary", "--", str(probe)],
        capture_output=True, text=True, timeout=60, check=False,
      )
    except (OSError, subprocess.SubprocessError) as error:
      raise MigrationError("ClamAV signature compatibility check failed") from error
    if result.returncode != 0 or result.stdout.strip() != str(probe) + ": OK":
      raise MigrationError("ClamAV rejected the existing signature files")

    # The scan gate still requires a fresh, independently recorded successful
    # update. Never copy old update records or manufacture a new timestamp.
    if os.path.lexists(destination):
      return False
    try:
      os.rename(staged, destination)
    except OSError as error:
      raise MigrationError("Signature destination could not be initialized") from error
  return True


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--source", type=Path, required=True)
  parser.add_argument("--destination", type=Path, required=True)
  parser.add_argument("--scanner", type=Path, required=True)
  args = parser.parse_args()
  try:
    changed = migrate_signatures(args.source, args.destination, args.scanner)
  except MigrationError as error:
    parser.exit(1, str(error) + "\n")
  print("Compatible ClamAV signatures migrated; update required before scanning"
        if changed else "Existing signature destination preserved")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
