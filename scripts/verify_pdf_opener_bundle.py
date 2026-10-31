#!/usr/bin/env python3
"""Fail-closed pre-install validation of the standalone native PDF scan-handler app."""

import argparse
from pathlib import Path
import plistlib
import stat


EXPECTED_FILES = frozenset({
  "Contents/Info.plist",
  "Contents/MacOS/PDFOpener",
  "Contents/MacOS/MakePDFMagicDefault",
  "Contents/Resources/twilight-reading.png",
})
OPTIONAL_FILES = frozenset({"Contents/_CodeSignature/CodeResources"})
ALLOWED_DIRS = frozenset({
  "Contents", "Contents/MacOS", "Contents/Resources",
  "Contents/_CodeSignature",
})
EXECUTABLES = frozenset({
  "Contents/MacOS/PDFOpener", "Contents/MacOS/MakePDFMagicDefault",
})
DOCUMENT_TYPES = [{
  "CFBundleTypeName": "PDF document",
  "CFBundleTypeRole": "Viewer",
  "LSHandlerRank": "Owner",
  "LSItemContentTypes": ["com.adobe.pdf"],
}]
METADATA = {
  "CFBundleExecutable": "PDFOpener",
  "CFBundleIdentifier": "local.studio.brave-pdf-opener",
  "CFBundleName": "PDF Magic Opener",
  "CFBundleDisplayName": "PDF Magic Opener",
  "CFBundlePackageType": "APPL",
  "CFBundleVersion": "1",
  "CFBundleShortVersionString": "1.0",
  "LSMinimumSystemVersion": "13.0",
  "LSUIElement": True,
  "CFBundleDocumentTypes": DOCUMENT_TYPES,
}


def verify_bundle(app: Path) -> None:
  """Validate every staged entry before the caller installs or registers the app."""
  app = Path(app)
  if app.name != "PDF Magic Opener.app" or not stat.S_ISDIR(app.lstat().st_mode):
    raise ValueError("Expected a real PDF Magic Opener.app directory")

  files = set()
  for path in app.rglob("*"):
    relative = path.relative_to(app).as_posix()
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
      raise ValueError("Symlinks are not allowed in the staged app: " + relative)
    if stat.S_ISDIR(mode):
      if relative not in ALLOWED_DIRS:
        raise ValueError("Unexpected app directory: " + relative)
    elif stat.S_ISREG(mode):
      if relative not in EXPECTED_FILES | OPTIONAL_FILES:
        raise ValueError("Unexpected app file: " + relative)
      if path.stat().st_size == 0:
        raise ValueError("Empty app file: " + relative)
      if mode & (stat.S_ISUID | stat.S_ISGID | stat.S_IWOTH):
        raise ValueError("Unsafe file permissions: " + relative)
      files.add(relative)
    else:
      raise ValueError("Unsupported app entry: " + relative)

  missing = EXPECTED_FILES - files
  if missing:
    raise ValueError("Missing required app contents: " + ", ".join(sorted(missing)))
  for relative in EXECUTABLES:
    mode = (app / relative).stat().st_mode
    if not mode & stat.S_IXUSR:
      raise ValueError("Bundled executable is not executable: " + relative)

  try:
    with (app / "Contents/Info.plist").open("rb") as stream:
      info = plistlib.load(stream)
  except (OSError, ValueError, plistlib.InvalidFileException) as error:
    raise ValueError("Malformed app Info.plist") from error
  if not isinstance(info, dict) or any(info.get(k) != v for k, v in METADATA.items()):
    raise ValueError("Unexpected app identity, document type, or minimum macOS version")

  with (app / "Contents/Resources/twilight-reading.png").open("rb") as stream:
    if stream.read(8) != b"\x89PNG\r\n\x1a\n":
      raise ValueError("Missing or invalid bundled progress artwork")


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("app", type=Path, help="Staged PDF Magic Opener.app to verify")
  args = parser.parse_args()
  try:
    verify_bundle(args.app)
  except (ValueError, OSError) as error:
    parser.exit(1, f"Bundle pre-install verification failed: {error}\n")
  print("Verified native PDF opener bundle and executable permissions")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
