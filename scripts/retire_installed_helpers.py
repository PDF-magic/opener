#!/usr/bin/env python3
"""Record installed PDF Magic native helpers and retire only unchanged binaries.

The record is created by the trusted per-user installer. Uninstall is opt-in,
after the PDF handler, Finder action, and native hosts have been disconnected.
No scanner settings, Python scripts, signature data, or third-party tools are removed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

HELPERS = (
  "launch-scanned-file",
  "resolve-default-browser",
  "discover-installed-browsers",
  "installed-applications",
  "identify-pdf-handler",
  "detect-pdf-handler-change",
  "pdf-handler-history",
  "verify-pdf-target",
  "select-custom-pdf-application",
  "browser-preference-list",
)
RECORD = ".pdf-magic-native-helpers.json"
MAX_SIZE = 64 * 1024 * 1024
MACHO_MAGIC = {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf",
               b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xce",
               b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
               b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"}
HEX = re.compile(r"[0-9a-f]{64}\Z")


class HelperRemovalRefused(ValueError):
  pass


def support_directory(home):
  home = Path(home)
  if not home.is_absolute() or ".." in home.parts:
    raise HelperRemovalRefused("Expected an absolute home directory")
  path = home
  for part in (None, "Library", "Application Support", "Studio", "allow-and-open"):
    if part is not None:
      path = path / part
    try:
      metadata = path.lstat()
    except FileNotFoundError as error:
      raise HelperRemovalRefused("Missing installed support directory") from error
    if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
        or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)):
      raise HelperRemovalRefused("Unsafe or unowned support directory")
  return path


def checked_file(path, *, missing=False, executable=False):
  try:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
  except FileNotFoundError:
    if missing:
      return None
    raise HelperRemovalRefused("Missing managed helper or ownership record")
  except OSError as error:
    raise HelperRemovalRefused("Unsafe managed helper file") from error
  try:
    before = os.fstat(fd)
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
        or before.st_uid != os.getuid()
        or before.st_size > MAX_SIZE
        or (executable and (before.st_size < 4 or not before.st_mode & stat.S_IXUSR))):
      raise HelperRemovalRefused("Unrecognized or modified helper file")
    with os.fdopen(fd, "rb", closefd=False) as stream:
      content = stream.read(MAX_SIZE + 1)
    after = os.fstat(fd)
    if (len(content) > MAX_SIZE or before.st_dev != after.st_dev
        or before.st_ino != after.st_ino or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns):
      raise HelperRemovalRefused("Helper changed during inspection")
    if executable and content[:4] not in MACHO_MAGIC:
      raise HelperRemovalRefused("Unrecognized native executable")
    return hashlib.sha256(content).hexdigest(), before
  finally:
    os.close(fd)


def read_record(directory):
  target = directory / RECORD
  result = checked_file(target)
  metadata = result[1]
  if stat.S_IMODE(metadata.st_mode) & 0o077:
    raise HelperRemovalRefused("Helper ownership record is not private")
  try:
    with target.open("r", encoding="utf-8") as stream:
      record = json.load(stream)
  except (OSError, UnicodeError, json.JSONDecodeError) as error:
    raise HelperRemovalRefused("Invalid helper ownership record") from error
  if (not isinstance(record, dict) or set(record) != {"version", "helpers"}
      or record["version"] != 1 or not isinstance(record["helpers"], dict)
      or set(record["helpers"]) != set(HELPERS)
      or any(not isinstance(v, str) or HEX.fullmatch(v) is None
             for v in record["helpers"].values())):
    raise HelperRemovalRefused("Unrecognized helper ownership record")
  return record["helpers"]


def record_installed_helpers(home):
  """Installer-only inventory of the exact ten compiled support executables."""
  directory = support_directory(home)
  if (directory / RECORD).exists() or (directory / RECORD).is_symlink():
    read_record(directory)  # Never overwrite an unsafe or customized record.
  digests = {name: checked_file(directory / name, executable=True)[0]
             for name in HELPERS}
  serialized = json.dumps({"version": 1, "helpers": digests},
                          sort_keys=True, indent=2) + "\n"
  staged = None
  try:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                     prefix=".pdf-magic-native-helpers.",
                                     delete=False) as stream:
      staged = Path(stream.name)
      os.fchmod(stream.fileno(), 0o600)
      stream.write(serialized)
      stream.flush()
      os.fsync(stream.fileno())
    # Reject an unexpected record created while staging.
    if (directory / RECORD).is_symlink():
      raise HelperRemovalRefused("Ownership record changed during installation")
    os.replace(staged, directory / RECORD)
  finally:
    if staged is not None:
      staged.unlink(missing_ok=True)
  return "Recorded ten verified installed native helper executables."


def inspect_installed_helpers(home, *, remove=False):
  directory = support_directory(home)
  expected = read_record(directory)
  found = {}
  # Preflight every recorded target BEFORE removing any. Absent targets are
  # idempotent, but an unexpected target is always a refusal.
  for name in HELPERS:
    result = checked_file(directory / name, missing=True, executable=True)
    if result is not None:
      if result[0] != expected[name]:
        raise HelperRemovalRefused("Modified helper executable; no files removed: " + name)
      found[name] = result[1]
  if not remove:
    return f"{len(found)} verified native helpers remain; rerun with --remove."
  for name, previous in found.items():
    path = directory / name
    result = checked_file(path, missing=False, executable=True)
    current = result[1]
    if (result[0] != expected[name] or current.st_ino != previous.st_ino
        or current.st_dev != previous.st_dev):
      raise HelperRemovalRefused("Helper changed during cleanup: " + name)
    # A final identity check prevents deleting a substituted pathname.
    latest = path.lstat()
    if (latest.st_ino != current.st_ino or latest.st_dev != current.st_dev
        or not stat.S_ISREG(latest.st_mode)):
      raise HelperRemovalRefused("Helper pathname changed during cleanup: " + name)
    path.unlink()
  return f"Removed {len(found)} verified native helper executables; retained user settings and ownership record."


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  mode = parser.add_mutually_exclusive_group()
  mode.add_argument("--record-install", action="store_true", help=argparse.SUPPRESS)
  mode.add_argument("--remove", action="store_true",
                    help="Remove only unchanged recorded helpers after integrations are disconnected")
  args = parser.parse_args(argv)
  if os.geteuid() == 0:
    parser.exit(1, "Do not run helper maintenance as root or with sudo.\n")
  try:
    if args.record_install:
      print(record_installed_helpers(Path.home()))
    else:
      if args.remove:
        answer = input("After restoring your PDF handler and disconnecting integrations, type REMOVE: ")
        if answer != "REMOVE":
          raise HelperRemovalRefused("Removal not confirmed")
      print(inspect_installed_helpers(Path.home(), remove=args.remove))
  except (HelperRemovalRefused, OSError, EOFError) as error:
    parser.exit(1, f"PDF Magic helper cleanup refused: {error}\n")


if __name__ == "__main__":
  main()
