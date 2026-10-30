#!/usr/bin/env python3
"""Opt-in, per-user macOS Chrome native messaging host registration."""

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

HOST_NAME = json.loads((Path(__file__).parent / "host-identity.json").read_text(encoding="utf-8"))["name"]
CHROME_DIRECTORY = Path("Library/Application Support/Google/Chrome/NativeMessagingHosts")
EXTENSION_ID = re.compile(r"[a-p]{32}\Z", re.ASCII)


def build_manifest(host_path, extension_ids):
  """Create Chrome's exact stdio manifest, never a wildcard allowlist."""
  binary = Path(host_path)
  if not binary.is_absolute() or binary.is_symlink():
    raise ValueError("Host executable must be an absolute, non-symlink path")
  try:
    mode = binary.stat().st_mode
  except OSError as exc:
    raise ValueError("Host executable does not exist") from exc
  if not stat.S_ISREG(mode) or not (mode & 0o111) or not os.access(binary, os.X_OK):
    raise ValueError("Host executable must be a regular executable file")
  ids = list(extension_ids)
  if not ids or any(not isinstance(value, str) or not EXTENSION_ID.fullmatch(value) for value in ids):
    raise ValueError("Provide actual approved 32-character Chrome extension IDs (a-p only)")
  return {
    "name": HOST_NAME,
    "description": "PDF Magic Opener native messaging host (transport only)",
    "path": str(binary),
    "type": "stdio",
    "allowed_origins": [f"chrome-extension://{value}/" for value in dict.fromkeys(ids)],
  }


def register(host_path, extension_ids, home):
  """Publish one registration without replacing any other user's configuration."""
  manifest = build_manifest(host_path, extension_ids)
  home = Path(home)
  if not home.is_absolute() or not home.is_dir():
    raise ValueError("An existing absolute home directory is required")
  directory = home
  for component in CHROME_DIRECTORY.parts:
    directory = directory / component
    if directory.is_symlink():
      raise ValueError("Refusing a symlink in the Chrome registration directory")
    if directory.exists() and not directory.is_dir():
      raise ValueError("Chrome registration directory contains a non-directory component")
    directory.mkdir(mode=0o700, exist_ok=True)
  target = directory / f"{HOST_NAME}.json"
  content = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
  if target.is_symlink():
    raise FileExistsError("Refusing to replace a symlink registration")
  if target.exists():
    if target.is_file() and target.read_bytes() == content:
      return target, False
    raise FileExistsError("Chrome host registration already exists with different contents")
  temporary = None
  try:
    with tempfile.NamedTemporaryFile(prefix=".pdfmagic-host-", dir=directory, delete=False) as output:
      temporary = Path(output.name)
      os.fchmod(output.fileno(), 0o600)
      output.write(content)
      output.flush()
      os.fsync(output.fileno())
    # Exclusive hard link makes publication atomic and never overwrites a pre-existing file.
    os.link(temporary, target)
  except FileExistsError as exc:
    if target.is_file() and not target.is_symlink() and target.read_bytes() == content:
      return target, False
    raise FileExistsError("Chrome host registration already exists with different contents") from exc
  finally:
    if temporary is not None:
      temporary.unlink(missing_ok=True)
  return target, True


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--host-path", required=True, type=Path,
                      help="absolute path to the already-compiled executable")
  parser.add_argument("--extension-id", required=True, action="append",
                      help="approved Chrome extension ID; repeat for additional IDs")
  args = parser.parse_args(argv)
  if sys.platform != "darwin":
    parser.error("this registration command targets Google Chrome on macOS")
  try:
    target, created = register(args.host_path, args.extension_id, Path.home())
  except (OSError, ValueError) as exc:
    parser.error(str(exc))
  print(f"{'Registered' if created else 'Already registered'} Chrome host: {target}")


if __name__ == "__main__":
  main()
