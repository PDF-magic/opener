#!/usr/bin/env python3
"""Package and validate an unsigned Safari Web Extension host-app ZIP."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import tempfile
import zipfile

SOURCE = Path(__file__).resolve().parents[1] / "extensions" / "webextension"
HOST = "PDFMagicOpener.app/"
APPEX = "Contents/PlugIns/PDFMagicOpenerSafari.appex/Contents/"
RESOURCES = ("manifest.json", "background.js", "popup.html", "popup.css",
             *(f"icons/icon-{n}.png" for n in (16, 32, 48, 128)))
EXECUTABLES = ("Contents/MacOS/PDFMagicOpener",
               APPEX + "MacOS/PDFMagicOpenerSafari")
ALLOWED = frozenset((
  "Contents/Info.plist", "Contents/PkgInfo",
  "Contents/MacOS/PDFMagicOpener",
  "Contents/Resources/LICENSE",
  "Contents/Resources/PDFMagicOpenerIcon.icns",
  "Contents/Resources/protection-performance.json",
  "Contents/Resources/Assets.car",
  APPEX + "Info.plist", APPEX + "PkgInfo",
  APPEX + "MacOS/PDFMagicOpenerSafari",
  *(APPEX + "Resources/" + name for name in RESOURCES),
))
REQUIRED = frozenset((
  "Contents/Info.plist", *EXECUTABLES, APPEX + "Info.plist",
  *(APPEX + "Resources/" + name for name in RESOURCES),
))
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024


def validate(files):
  """Require an exact known bundle shape and byte-identical inactive assets."""
  if not REQUIRED.issubset(files) or not files.keys() <= ALLOWED:
    raise ValueError("Missing or unexpected Safari app contents")
  if any(not b or len(b) > MAX_FILE for b in files.values()):
    raise ValueError("Empty or oversized Safari bundle file")
  if sum(map(len, files.values())) > MAX_TOTAL:
    raise ValueError("Oversized Safari bundle")
  host = plistlib.loads(files["Contents/Info.plist"])
  appex = plistlib.loads(files[APPEX + "Info.plist"])
  if (host.get("CFBundleIdentifier") != "local.studio.pdfmagicopener.swiftui"
      or host.get("CFBundlePackageType") != "APPL"
      or "CFBundleDocumentTypes" in host):
    raise ValueError("Unexpected host app identity or PDF handler registration")
  if (appex.get("CFBundleIdentifier") != "local.studio.pdfmagicopener.swiftui.safari"
      or appex.get("CFBundlePackageType") != "XPC!"
      or appex.get("NSExtension", {}).get("NSExtensionPointIdentifier")
      != "com.apple.Safari.web-extension"):
    raise ValueError("Unexpected Safari extension identity")
  manifest_bytes = files[APPEX + "Resources/manifest.json"]
  if manifest_bytes != (SOURCE / "manifest.json").read_bytes():
    raise ValueError("Safari manifest differs from shared source")
  manifest = json.loads(manifest_bytes)
  if (manifest.get("manifest_version") != 3
      or manifest.get("incognito") != "not_allowed"
      or manifest.get("permissions") != []
      or manifest.get("host_permissions") != []
      or manifest.get("optional_permissions") != ["downloads"]
      or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", manifest.get("version", ""))
      or manifest.get("background") !=
      {"service_worker": "background.js", "type": "module"}
      or manifest.get("action", {}).get("default_title")
      != "PDF Magic Opener (not active)"):
    raise ValueError("Unsafe Safari package manifest")
  for name in RESOURCES:
    src = SOURCE / (name if name == "manifest.json" or name.startswith("icons/")
                    else "src/" + name)
    if files[APPEX + "Resources/" + name] != src.read_bytes():
      raise ValueError("Modified Safari extension asset: " + name)
  return manifest["version"]


def read_app(app):
  if app.is_symlink() or not app.is_dir() or app.name != "PDFMagicOpener.app":
    raise ValueError("Expected a real Xcode-built PDFMagicOpener.app")
  files = {}
  for path in app.rglob("*"):
    if path.is_symlink():
      raise ValueError("Symlink in Safari bundle")
    relative = path.relative_to(app).as_posix()
    if path.is_dir():
      if not any(name.startswith(relative + "/") for name in ALLOWED):
        raise ValueError("Unexpected Safari bundle directory: " + relative)
      continue
    if not path.is_file() or relative not in ALLOWED:
      raise ValueError("Unexpected Safari bundle file: " + relative)
    if path.stat().st_size > MAX_FILE:
      raise ValueError("Oversized Safari bundle file")
    files[relative] = path.read_bytes()
  version = validate(files)
  for path in EXECUTABLES:
    if not (app / path).stat().st_mode & stat.S_IXUSR:
      raise ValueError("Missing executable bit: " + path)
  return files, version


def verify_archive(archive):
  if archive.is_symlink() or not archive.is_file():
    raise ValueError("Missing Safari ZIP")
  with zipfile.ZipFile(archive) as bundle:
    infos = bundle.infolist()
    names = [entry.filename for entry in infos]
    if (len(infos) > len(ALLOWED) or len(names) != len(set(names))
        or names != sorted(names) or bundle.testzip() is not None):
      raise ValueError("Malformed Safari ZIP")
    files = {}
    for entry in infos:
      if not entry.filename.startswith(HOST):
        raise ValueError("Safari ZIP escapes the host app")
      name = entry.filename[len(HOST):]
      mode = entry.external_attr >> 16
      if (name not in ALLOWED or entry.is_dir()
          or not stat.S_ISREG(mode) or entry.file_size > MAX_FILE
          or (name in EXECUTABLES and not mode & stat.S_IXUSR)):
        raise ValueError("Unexpected Safari ZIP entry: " + entry.filename)
      files[name] = bundle.read(entry)
    return validate(files)


def package(app, output):
  files, version = read_app(app)
  if output.exists() and (output.is_symlink() or not output.is_dir()):
    raise ValueError("Unsafe package output directory")
  output.mkdir(parents=True, exist_ok=True)
  destination = output / f"pdf-magic-opener-safari-{version}-unsigned.zip"
  fd, name = tempfile.mkstemp(prefix=".safari-", suffix=".zip", dir=output)
  temporary = Path(name)
  try:
    with os.fdopen(fd, "wb") as stream:
      with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED,
                           compresslevel=9, allowZip64=False) as bundle:
        for path, data in sorted(files.items()):
          info = zipfile.ZipInfo(HOST + path, date_time=(1980, 1, 1, 0, 0, 0))
          info.create_system = 3
          info.external_attr = ((stat.S_IFREG |
                                 (0o755 if path in EXECUTABLES else 0o644)) << 16)
          info.compress_type = zipfile.ZIP_DEFLATED
          bundle.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED,
                          compresslevel=9)
    if verify_archive(temporary) != version:
      raise ValueError("Safari ZIP verification failed")
    os.replace(temporary, destination)
  finally:
    temporary.unlink(missing_ok=True)
  return destination


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--app", type=Path)
  parser.add_argument("--output-dir", type=Path)
  parser.add_argument("--verify", type=Path)
  args = parser.parse_args()
  if args.verify is not None and args.app is None and args.output_dir is None:
    print("Verified Safari ZIP:", verify_archive(args.verify))
  elif args.verify is None and args.app is not None and args.output_dir is not None:
    print("Unsigned Safari package:", package(args.app, args.output_dir))
  else:
    parser.error("Use --verify ZIP or --app APP --output-dir DIRECTORY")


if __name__ == "__main__":
  main()
