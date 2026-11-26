#!/usr/bin/env python3
"""Audit tracked native test paths without executing application or fixture code."""

from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LEGACY = re.compile(r"\btest-[A-Za-z0-9_-]+\.(?:swift|applescript)\b")
NATIVE_PATH = re.compile(r"\btests/(?:[A-Za-z0-9_-]+/)+[A-Za-z0-9_.-]+\.(?:swift|applescript)\b")


def audit(root):
  raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
  paths = sorted({p.decode("utf-8") for p in raw.split(b"\0") if p})
  tracked = set(paths)
  errors = []
  scanned = 0
  for name in paths:
    path = root / name
    if not path.is_file() or path.is_symlink():
      if not path.is_symlink():
        errors.append(f"Missing tracked file: {name}")
      continue
    if "/" not in name and LEGACY.fullmatch(name):
      errors.append(f"Root-level native test: {name}")
    data = path.read_bytes()
    if b"\0" in data:
      continue
    try:
      source = data.decode("utf-8")
    except UnicodeDecodeError:
      continue
    scanned += 1
    for line_number, line in enumerate(source.splitlines(), 1):
      for match in LEGACY.finditer(line):
        errors.append(f"{name}:{line_number}: obsolete test reference {match.group()}")
      for match in NATIVE_PATH.finditer(line):
        if match.group() not in tracked:
          errors.append(f"{name}:{line_number}: missing native test {match.group()}")
  return scanned, len(paths), errors


if __name__ == "__main__":
  scanned, total, errors = audit(ROOT)
  print(f"Audited {scanned} UTF-8 text files out of {total} tracked files.")
  for error in errors:
    print(error, file=sys.stderr)
  raise SystemExit(bool(errors))
