#!/usr/bin/env python3
"""Durable, resumable installation-migration journal (opener-0949).

This journal records installer progress only. It never declares signatures
fresh, selects an application, or changes the scanner and Finder workflows.
"""

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import time

DIRECTORIES = ("Library", "Application Support", "Studio", "allow-and-open")
MARKER = ".installation-migration.json"
LOCK = ".installation-migration.lock"
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
TOKEN = re.compile(r"^[0-9a-f]{32}$")


class MigrationStateError(ValueError):
  pass


def _check_directory(fd):
  info = os.fstat(fd)
  if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
      or info.st_mode & 0o022):
    raise MigrationStateError("Unsafe migration-state directory")


def _open_directory(home, *, create):
  fd = os.open(home, DIRECTORY_FLAGS)
  try:
    _check_directory(fd)
    for component in DIRECTORIES:
      try:
        child = os.open(component, DIRECTORY_FLAGS, dir_fd=fd)
      except FileNotFoundError:
        if not create:
          os.close(fd)
          return None
        try:
          os.mkdir(component, 0o700, dir_fd=fd)
        except FileExistsError:
          pass
        child = os.open(component, DIRECTORY_FLAGS, dir_fd=fd)
      try:
        _check_directory(child)
      except BaseException:
        os.close(child)
        raise
      os.close(fd)
      fd = child
    return fd
  except BaseException:
    os.close(fd)
    raise


def _read(fd):
  try:
    marker_fd = os.open(MARKER, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
  except FileNotFoundError:
    return None, None
  with os.fdopen(marker_fd, "rb") as stream:
    info = os.fstat(stream.fileno())
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
        or info.st_uid != os.getuid() or info.st_mode & 0o077
        or not 0 < info.st_size <= 2048):
      raise MigrationStateError("Unsafe migration-state marker")
    raw = stream.read(2049)
  try:
    record = json.loads(raw)
  except (UnicodeDecodeError, ValueError) as error:
    raise MigrationStateError("Malformed migration-state marker") from error
  if (not isinstance(record, dict)
      or set(record) != {"version", "phase", "attempt", "last_completed"}
      or type(record["version"]) is not int or record["version"] != 1
      or record["phase"] not in ("running", "complete")
      or not isinstance(record["attempt"], str)
      or not TOKEN.fullmatch(record["attempt"])
      or (record["last_completed"] is not None
          and (type(record["last_completed"]) is not int
               or record["last_completed"] < 0))
      or (record["phase"] == "complete" and record["last_completed"] is None)):
    raise MigrationStateError("Unsupported migration-state marker")
  return record, (info.st_dev, info.st_ino)


def _lock(fd):
  lock_fd = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=fd)
  info = os.fstat(lock_fd)
  if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
      or info.st_uid != os.getuid() or info.st_mode & 0o077):
    os.close(lock_fd)
    raise MigrationStateError("Unsafe migration-state lock")
  fcntl.flock(lock_fd, fcntl.LOCK_EX)
  return lock_fd


def _save(fd, record, identity):
  temporary = "." + MARKER + "." + secrets.token_hex(12) + ".tmp"
  temporary_fd = os.open(
    temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
    0o600, dir_fd=fd,
  )
  try:
    with os.fdopen(temporary_fd, "wb") as stream:
      stream.write((json.dumps(record, sort_keys=True) + "\n").encode("ascii"))
      stream.flush()
      os.fsync(stream.fileno())
    try:
      current = os.stat(MARKER, dir_fd=fd, follow_symlinks=False)
      observed = (current.st_dev, current.st_ino)
    except FileNotFoundError:
      observed = None
    if observed != identity:
      raise MigrationStateError("Migration-state marker changed during update")
    os.replace(temporary, MARKER, src_dir_fd=fd, dst_dir_fd=fd)
    os.fsync(fd)
  finally:
    try:
      os.unlink(temporary, dir_fd=fd)
    except FileNotFoundError:
      pass


def status(home):
  """Read-only status, without creating a directory or changing installation."""
  fd = _open_directory(home, create=False)
  if fd is None:
    return "not_started"
  try:
    record, _ = _read(fd)
    if record is None:
      return "not_started"
    return "partial" if record["phase"] == "running" else "complete"
  finally:
    os.close(fd)


def begin(home):
  """Start a new attempt; keep the prior success when resuming or reinstalling."""
  fd = _open_directory(home, create=True)
  try:
    lock_fd = _lock(fd)
    try:
      previous, identity = _read(fd)
      if previous is not None and previous["phase"] == "running":
        print("Resuming partially completed migration; revalidating installer steps.",
              file=sys.stderr)
      attempt = secrets.token_hex(16)
      record = {
        "version": 1, "phase": "running", "attempt": attempt,
        "last_completed": previous["last_completed"] if previous else None,
      }
      _save(fd, record, identity)
      return attempt
    finally:
      os.close(lock_fd)
  finally:
    os.close(fd)


def complete(home, attempt):
  """Complete only this attempt, after every installer operation succeeds."""
  if not TOKEN.fullmatch(attempt):
    raise MigrationStateError("Invalid migration attempt")
  fd = _open_directory(home, create=False)
  if fd is None:
    raise MigrationStateError("Migration was not started")
  try:
    lock_fd = _lock(fd)
    try:
      record, identity = _read(fd)
      if record is None or record["attempt"] != attempt:
        raise MigrationStateError("Migration attempt is missing or superseded")
      if record["phase"] == "complete":
        return
      record["phase"] = "complete"
      record["last_completed"] = max(int(time.time()), record["last_completed"] or 0)
      _save(fd, record, identity)
    finally:
      os.close(lock_fd)
  finally:
    os.close(fd)


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--home", type=Path, default=Path.home())
  parser.add_argument("action", choices=("status", "begin", "complete"))
  parser.add_argument("attempt", nargs="?")
  args = parser.parse_args()
  try:
    if args.action == "status":
      print(status(args.home))
    elif args.action == "begin":
      print(begin(args.home))
    else:
      if args.attempt is None:
        parser.error("complete requires the attempt returned by begin")
      complete(args.home, args.attempt)
      print("complete")
  except (OSError, MigrationStateError) as error:
    print(f"Installation migration state refused: {error}", file=sys.stderr)
    return 1
  return 0


if __name__ == "__main__":
  sys.exit(main())
