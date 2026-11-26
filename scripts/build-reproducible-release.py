#!/usr/bin/env python3
"""Build and compare isolated, unsigned browser release candidates (opener-1136)."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from zipfile import ZipFile, ZIP_STORED

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "extensions/webextension"
SOURCES = (
  "manifest.json", "firefox/gecko.json",
  "src/background.js", "src/popup.html", "src/popup.css",
  "src/intercept-scan-failed.html", "src/intercept-scan-failed.css",
  "icons/icon-16.png", "icons/icon-32.png",
  "icons/icon-48.png", "icons/icon-128.png",
  "scripts/build.mjs", "scripts/build-firefox.mjs",
  "scripts/package-chrome.mjs", "scripts/package-firefox.mjs",
  "scripts/chrome-zip.mjs", "scripts/popup-assets.mjs",
  "scripts/intercept-scan-failed-assets.mjs",
)
ARCHIVE_FILES = (
  "manifest.json", "background.js", "popup.html", "popup.css",
  "intercept-scan-failed.html", "intercept-scan-failed.css",
  "icons/icon-16.png", "icons/icon-32.png",
  "icons/icon-48.png", "icons/icon-128.png",
)
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")


class BuildError(Exception):
  """Release candidate validation failed without permitting publication."""


def stage_sources(source, destination):
  """Only read exact reviewed paths; never read credentials, tests, or stale dist."""
  for name in SOURCES:
    path = source
    parts = name.split("/")
    for part in parts[:-1]:
      path = path / part
      if not stat.S_ISDIR(path.lstat().st_mode):
        raise BuildError("Untrusted build input directory")
    path = path / parts[-1]
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= 2 * 1024 * 1024:
      raise BuildError("Missing or unsafe approved build source")
    target = destination / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)


def release_version(source):
  value = json.loads((source / "manifest.json").read_text(encoding="utf-8"))["version"]
  if not isinstance(value, str) or not VERSION.fullmatch(value):
    raise BuildError("Invalid candidate version")
  return value


def artifact_names(version):
  return (
    "chrome/pdf-magic-opener-chrome-" + version + ".zip",
    "firefox/pdf-magic-opener-firefox-" + version + "-unsigned.zip",
  )


def verify_zip(path, manifest):
  if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 8 * 1024 * 1024:
    raise BuildError("Missing or unsafe ZIP archive")
  with ZipFile(path) as archive:
    if archive.namelist() != list(ARCHIVE_FILES) or archive.comment or archive.testzip():
      raise BuildError("Unexpected or corrupt ZIP contents")
    for info in archive.infolist():
      if info.compress_type != ZIP_STORED or info.flag_bits & 1 or info.date_time != (1980, 1, 1, 0, 0, 0):
        raise BuildError("Archive has variable timestamps or unexpected compression")
    if json.loads(archive.read("manifest.json")) != manifest:
      raise BuildError("Archive manifest disagrees with validated build")


def build_once(source, directory):
  web = directory / "webextension"
  stage_sources(source, web)
  version = release_version(web)
  for command in ("package-chrome.mjs", "package-firefox.mjs"):
    try:
      subprocess.run(["node", "scripts/" + command], cwd=web, check=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
      raise BuildError("Existing browser package validator rejected build") from error
  chrome, firefox = artifact_names(version)
  chrome_manifest = json.loads((web / "manifest.json").read_text(encoding="utf-8"))
  firefox_manifest = json.loads((web / "dist/firefox/manifest.json").read_text(encoding="utf-8"))
  if (firefox_manifest.get("version") != version or
      firefox_manifest.get("browser_specific_settings", {}).get("gecko", {}).get("id") !=
      "pdf-magic-opener@example.invalid"):
    raise BuildError("Firefox candidate differs from inactive development identity")
  output = {
    chrome: web / "dist/chrome" / Path(chrome).name,
    firefox: web / "dist/firefox-packages" / Path(firefox).name,
  }
  verify_zip(output[chrome], chrome_manifest)
  verify_zip(output[firefox], firefox_manifest)
  return {name: path.read_bytes() for name, path in output.items()}


def require_identical(first, second):
  if first.keys() != second.keys() or any(first[name] != second[name] for name in first):
    raise BuildError("Independent unsigned release candidates differ")


def build_release(output, source=WEB):
  if output.exists() or output.is_symlink():
    raise BuildError("Output exists; refusing to overwrite user files")
  with tempfile.TemporaryDirectory(prefix="pdfmagic-release-") as scratch:
    first = build_once(source, Path(scratch) / "first")
    second = build_once(source, Path(scratch) / "second")
    require_identical(first, second)
    output.mkdir(parents=True, exist_ok=False)
    try:
      lines = []
      for name in sorted(first):
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(first[name])
        lines.append(hashlib.sha256(first[name]).hexdigest() + "  " + name + "\n")
      (output / "SHA256SUMS").write_text("".join(lines), encoding="ascii")
    except BaseException:
      shutil.rmtree(output)
      raise
  return sorted(first)


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--output-dir", type=Path, required=True)
  args = parser.parse_args(argv)
  try:
    names = build_release(args.output_dir)
  except (BuildError, OSError, ValueError, KeyError) as error:
    detail = str(error) if isinstance(error, BuildError) else "invalid build input"
    print("Unsigned build refused: " + detail, file=sys.stderr)
    return 1
  print("Two clean builds matched: " + ", ".join(names))
  print("SHA256SUMS created. Signing and publication remain blocked.")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
