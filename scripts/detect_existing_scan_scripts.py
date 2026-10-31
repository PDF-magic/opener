#!/usr/bin/env python3
"""Detect previously installed scan entry points without reading or running them.

A migration preflight, not an installer or a scan-health check. The directory
and script names match the existing install-allow-and-open.sh layout.
"""
from pathlib import Path
import stat
import sys

SCAN_SCRIPTS = ("allow-and-open.sh", "scan-and-open.py")


def detect_existing_scan_scripts(install_dir):
  """Return installed scan-script names in a stable order, never their contents.

  Reject non-regular entries rather than silently treating a symlink or
  directory as a missing script before the installer copies replacements.
  """
  install_dir = Path(install_dir)
  try:
    directory_mode = install_dir.lstat().st_mode
  except FileNotFoundError:
    return ()
  if not stat.S_ISDIR(directory_mode):
    raise ValueError("unsafe existing scan-script directory")

  found = []
  for name in SCAN_SCRIPTS:
    try:
      entry_mode = (install_dir / name).lstat().st_mode
    except FileNotFoundError:
      continue
    if not stat.S_ISREG(entry_mode):
      raise ValueError(f"unsafe existing scan-script entry: {name}")
    found.append(name)
  return tuple(found)


def main(argv):
  if len(argv) != 2:
    print("usage: detect_existing_scan_scripts.py INSTALL_DIRECTORY", file=sys.stderr)
    return 2
  try:
    existing = detect_existing_scan_scripts(argv[1])
  except (OSError, ValueError):
    print("Existing scan-script detection failed; installation not started.", file=sys.stderr)
    return 1
  if existing:
    print("Existing scan scripts detected: " + ", ".join(existing))
  else:
    print("No existing scan scripts detected.")
  return 0


if __name__ == "__main__":
  raise SystemExit(main(sys.argv))
