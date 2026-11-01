#!/usr/bin/env python3
"""Package a validated macOS preferences app as a non-publishing release ZIP.

This command never installs software, registers PDF handling, signs code, or
changes the standalone PDF scanner. Signed/notarized distribution is separate.
"""
import argparse
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import tempfile
import zipfile

from package_application_helpers import (
  APP_NAME, HELPER_NAMES, NON_DISTRIBUTABLE_PARTS,
  NON_DISTRIBUTABLE_SUFFIXES, validate_helpers,
)

REQUIRED = frozenset({
  f"{APP_NAME}/Contents/Info.plist",
  f"{APP_NAME}/Contents/MacOS/PDFMagicOpener",
  *(f"{APP_NAME}/Contents/Helpers/{name}" for name in HELPER_NAMES),
})


def _validate_name(name):
  """Reject paths that escape the single app or contain forbidden resources."""
  if not name or "\\" in name or "\x00" in name or name.startswith("/"):
    raise ValueError("Unsafe ZIP entry path")
  components = name.rstrip("/").split("/")
  if any(part in ("", ".", "..") for part in components):
    raise ValueError("Unsafe ZIP entry path")
  if name == "__MACOSX/":
    return
  if components[:2] == ["__MACOSX", "._" + APP_NAME]:
    if len(components) == 2:
      return
  if components[0] == "__MACOSX":
    if len(components) < 2 or components[1] != APP_NAME:
      raise ValueError("Unexpected resource-fork ZIP entry")
    relative = components[2:]
  else:
    if components[0] != APP_NAME:
      raise ValueError("ZIP contains an unexpected top-level entry")
    relative = components[1:]
  if (any(part.casefold() in NON_DISTRIBUTABLE_PARTS for part in relative)
      or any(PurePosixPath(part).suffix.casefold() in NON_DISTRIBUTABLE_SUFFIXES
             for part in relative)):
    raise ValueError("Non-distributable resource in ZIP")


def _validate_symlink(name, target):
  if not target or target.startswith("/") or "\\" in target or "\x00" in target:
    raise ValueError("Unsafe archived symlink")
  parts = list(PurePosixPath(name).parent.parts)
  for component in target.split("/"):
    if component in ("", "."):
      continue
    if component == "..":
      if len(parts) <= 1:
        raise ValueError("Archived symlink escapes application bundle")
      parts.pop()
    else:
      parts.append(component)
  if parts[0] != APP_NAME:
    raise ValueError("Archived symlink escapes application bundle")


def verify_archive(archive):
  """Check ZIP integrity, one app, helper manifest and non-escaping links."""
  archive = Path(archive)
  if archive.is_symlink() or not archive.is_file() or archive.suffix.lower() != ".zip":
    raise ValueError("Expected a regular ZIP archive")
  try:
    with zipfile.ZipFile(archive, "r") as package:
      members = package.infolist()
      names = [member.filename for member in members]
      if len(names) != len(set(names)):
        raise ValueError("Duplicate ZIP entries")
      for member in members:
        name = member.filename
        _validate_name(name)
        if name.startswith("__MACOSX/"):
          continue
        mode = member.external_attr >> 16
        if stat.S_ISLNK(mode):
          _validate_symlink(name, package.read(member).decode("utf-8"))
        elif stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
          raise ValueError("Unsupported archived file type")
      missing = REQUIRED - set(names)
      if missing:
        raise ValueError("Missing required application files: " + ", ".join(sorted(missing)))
      corrupt = package.testzip()
      if corrupt is not None:
        raise ValueError("Corrupt ZIP entry: " + corrupt)
  except (zipfile.BadZipFile, UnicodeError) as error:
    raise ValueError("Malformed release archive") from error
  return len(names)


def create_archive(app, output):
  """Use macOS ditto to retain app metadata, and publish atomically without overwrite."""
  app, output = Path(app), Path(output)
  validate_helpers(app)
  if output.suffix.lower() != ".zip" or output.exists() or output.is_symlink():
    raise ValueError("Output must be a new .zip file")
  parent = output.parent
  if not parent.is_dir() or parent.is_symlink():
    raise ValueError("Archive output parent must be an existing real directory")
  with tempfile.TemporaryDirectory(prefix=".pdfmagic-archive-", dir=parent) as temp:
    temporary = Path(temp) / "archive.zip"
    subprocess.run(
      ["/usr/bin/ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
       str(app.resolve()), str(temporary)],
      check=True,
    )
    verify_archive(temporary)
    # Linking in the same directory is atomic and cannot replace an existing ZIP.
    os.link(temporary, output)
  return output


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--app", type=Path)
  parser.add_argument("--output", type=Path)
  parser.add_argument("--verify", type=Path)
  args = parser.parse_args()
  try:
    if args.verify is not None and args.app is None and args.output is None:
      print("Verified macOS release ZIP entries:", verify_archive(args.verify))
    elif args.verify is None and args.app is not None and args.output is not None:
      print("Created unsigned macOS release ZIP:", create_archive(args.app, args.output))
    else:
      parser.error("Use --app APP --output ZIP or --verify ZIP")
  except (ValueError, OSError, subprocess.CalledProcessError) as error:
    parser.exit(1, f"Release archive validation failed: {error}\n")


if __name__ == "__main__":
  main()
