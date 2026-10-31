#!/usr/bin/env python3
"""Stage a macOS application with reviewed, native helper executables.

This is a packaging operation only. It never registers a PDF handler, alters
an installed helper, or enables browser native-messaging permissions.
"""
import argparse
import os
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "PDFMagicOpener.app"
BUNDLE_ID = "local.studio.pdfmagicopener.swiftui"
HELPER_FOLDER = Path("Contents/Helpers")
# Match the existing installer compilation inputs and conditional entry points.
# The separately installed PDFOpener scan gate is intentionally NOT embedded.
HELPERS = (
  ("launch-scanned-file", (), ("launch-scanned-file.swift",)),
  ("resolve-default-browser", (), ("resolve-default-browser.swift",)),
  ("discover-installed-browsers", (), ("discover-installed-browsers.swift",)),
  ("installed-applications", (), ("installed-applications.swift",)),
  ("identify-pdf-handler", (), ("identify-pdf-handler.swift",)),
  ("detect-pdf-handler-change", ("-D", "PDF_HANDLER_TESTING"),
   ("identify-pdf-handler.swift", "detect-pdf-handler-change.swift")),
  ("pdf-handler-history", (), ("pdf-handler-history.swift",)),
  ("verify-pdf-target", (), ("verify-pdf-target.swift",)),
  ("select-custom-pdf-application", ("-D", "PDF_TARGET_TESTING"),
   ("verify-pdf-target.swift", "select-custom-pdf-application.swift")),
  ("browser-preference-list",
   ("-D", "BROWSER_DISCOVERY_TESTING", "-D", "BROWSER_METADATA_TESTING"),
   ("browser-preference-list.swift", "browser-preference-live-refresh.swift",
    "discover-installed-browsers.swift", "browser-app-metadata.swift")),
  ("pdf-magic-native-host", (),
   ("native-messaging/Host.swift", "native-messaging/HostStatus.swift",
    "native-messaging/CallerOrigin.swift",
    "native-messaging/NativeCallerAdmission.swift")),
)
HELPER_NAMES = frozenset(spec[0] for spec in HELPERS)
MACHO_MAGIC = frozenset((b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf",
                         b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xce",
                         b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
                         b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"))
MAX_HELPER_BYTES = 64 * 1024 * 1024


def inspect_app(app):
  """Require the exact preferences app identity, not the PDF scanner bundle."""
  if app.is_symlink() or not app.is_dir() or app.name != APP_NAME:
    raise ValueError("Expected a real Xcode-built PDFMagicOpener.app")
  info = app / "Contents/Info.plist"
  if info.is_symlink() or not info.is_file():
    raise ValueError("Missing safe application Info.plist")
  with info.open("rb") as stream:
    plist = plistlib.load(stream)
  if (plist.get("CFBundleIdentifier") != BUNDLE_ID
      or plist.get("CFBundlePackageType") != "APPL"
      or plist.get("CFBundleExecutable") != "PDFMagicOpener"
      or "CFBundleDocumentTypes" in plist
      or plist.get("LSUIElement", False) is not False):
    raise ValueError("Application identity must not change or register PDF handling")
  executable = app / "Contents/MacOS/PDFMagicOpener"
  if (executable.is_symlink() or not executable.is_file()
      or not os.access(executable, os.X_OK)):
    raise ValueError("Missing preferences application entry point")


def validate_helpers(app):
  """Reject missing, substituted, unexpected, or non-executable helpers."""
  inspect_app(app)
  directory = app / HELPER_FOLDER
  if directory.is_symlink() or not directory.is_dir():
    raise ValueError("Required helper directory is absent or unsafe")
  if {entry.name for entry in directory.iterdir()} != HELPER_NAMES:
    raise ValueError("Missing or unexpected application helper executables")
  for name in HELPER_NAMES:
    path = directory / name
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode)
        or not info.st_mode & stat.S_IXUSR
        or info.st_size < 4 or info.st_size > MAX_HELPER_BYTES):
      raise ValueError("Invalid helper executable: " + name)
    with path.open("rb") as binary:
      if binary.read(4) not in MACHO_MAGIC:
        raise ValueError("Non-Mach-O application helper: " + name)
  return sorted(HELPER_NAMES)


def stage(app, output, *, swiftc="/usr/bin/xcrun"):
  """Build reviewed Swift helpers into a separate, uninstalled staging copy."""
  inspect_app(app)
  if output.is_symlink() or (output.exists() and not output.is_dir()):
    raise ValueError("Unsafe packaging output directory")
  output.mkdir(parents=True, exist_ok=True)
  destination = output / APP_NAME
  if destination.exists() or destination.is_symlink():
    raise ValueError("Refusing to replace an existing packaged app")
  with tempfile.TemporaryDirectory(prefix=".pdfmagic-package-", dir=output) as temp:
    copy = Path(temp) / APP_NAME
    shutil.copytree(app, copy, symlinks=True)
    helpers = copy / HELPER_FOLDER
    if helpers.exists() or helpers.is_symlink():
      raise ValueError("Unexpected pre-existing helper directory")
    helpers.mkdir(mode=0o755)
    for name, definitions, paths in HELPERS:
      sources = [ROOT / path for path in paths]
      if any(not path.is_file() or path.is_symlink() for path in sources):
        raise ValueError("Missing or unsafe reviewed helper source: " + name)
      # The launch-scanned-file source retains its original top-level entry
      # expression; the other helper sources provide their own @main types.
      library_flags = [] if name == "launch-scanned-file" else ["-parse-as-library"]
      arguments = [swiftc, "swiftc", *library_flags, "-O",
                   *definitions, *(str(path) for path in sources),
                   "-o", str(helpers / name)]
      # No shell or user-controlled executable names/Swift flags.
      subprocess.run(arguments, check=True, cwd=ROOT)
      (helpers / name).chmod(0o755)
    validate_helpers(copy)
    # The original Xcode app and installed scanner remain unchanged.
    os.rename(copy, destination)
  return destination


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--app", type=Path)
  parser.add_argument("--output-dir", type=Path)
  parser.add_argument("--verify", type=Path)
  args = parser.parse_args()
  if args.verify is not None and args.app is None and args.output_dir is None:
    print("Verified packaged application helpers:", ", ".join(validate_helpers(args.verify)))
  elif args.verify is None and args.app is not None and args.output_dir is not None:
    result = stage(args.app, args.output_dir)
    print("Staged application with native helpers:", result)
  else:
    parser.error("Use --verify APP or --app APP --output-dir DIRECTORY")


if __name__ == "__main__":
  main()
