#!/usr/bin/env python3
"""Remove only matching, opt-in per-user native host registrations on uninstall.

No browser profiles, executable files, preferences or scanner state are changed.
The host executable may already be absent when this cleanup is run.
"""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parent
HOST_NAME = json.loads((ROOT / "host-identity.json").read_text(encoding="utf-8"))["name"]
MANIFEST_NAME = HOST_NAME + ".json"
CHROME_DIRECTORY = Path("Library/Application Support/Google/Chrome/NativeMessagingHosts")
# Explicit, reviewed macOS locations from register-chromium-hosts.py.
# Opera and Chrome share the same manifest. Do not remove it twice.
CHROMIUM_DIRECTORIES = {
  "chrome": CHROME_DIRECTORY,
  "chromium": Path("Library/Application Support/Chromium/NativeMessagingHosts"),
  "chrome-for-testing": Path("Library/Application Support/Google/ChromeForTesting/NativeMessagingHosts"),
  "brave": Path("Library/Application Support/BraveSoftware/Brave-Browser/NativeMessagingHosts"),
  "edge": Path("Library/Application Support/Microsoft Edge/NativeMessagingHosts"),
  "vivaldi": Path("Library/Application Support/Vivaldi/NativeMessagingHosts"),
  "opera": CHROME_DIRECTORY,
  "arc": Path("Library/Application Support/Arc/User Data/NativeMessagingHosts"),
}
FIREFOX_MAC_DIRECTORY = Path("Library/Application Support/Mozilla/NativeMessagingHosts")
FIREFOX_LINUX_DIRECTORY = Path(".mozilla/native-messaging-hosts")
CHROME_ID = re.compile(r"[a-p]{32}\Z", re.ASCII)
FIREFOX_DEVELOPMENT_ID = "pdf-magic-opener@example.invalid"


def validate_original_host_path(value):
  """Check exact spelling and existing ancestors even after host uninstall."""
  raw = os.fspath(value)
  if (not isinstance(raw, str) or not raw.startswith("/") or
      len(raw.encode("utf-8")) > 4096 or
      os.path.normpath(raw) != raw or
      any(ord(char) < 32 or ord(char) == 127 for char in raw) or
      any(part in (".", "..") for part in raw.split("/"))):
    raise ValueError("Unsafe supplied original host path")
  current = Path("/")
  for component in (part for part in raw.split("/") if part):
    current /= component
    try:
      mode = current.lstat().st_mode
    except FileNotFoundError:
      break
    except OSError as exc:
      raise ValueError("Supplied host path is inaccessible") from exc
    if stat.S_ISLNK(mode):
      raise ValueError("Symlink in supplied original host path")
  return Path(raw)


def _expected_manifest(browser, host_path, extension_ids, development):
  if HOST_NAME != "org.pdfmagic.opener":
    raise ValueError("Unreviewed native host identity")
  if browser in CHROMIUM_DIRECTORIES:
    ids = list(extension_ids)
    if not ids or any(type(item) is not str or not CHROME_ID.fullmatch(item)
                      for item in ids):
      raise ValueError("Chrome cleanup requires every exact approved extension ID")
    return {
      "name": HOST_NAME,
      "description": "PDF Magic Opener native messaging host (transport only)",
      "path": str(host_path),
      "type": "stdio",
      "allowed_origins": [f"chrome-extension://{item}/" for item in dict.fromkeys(ids)],
    }
  if browser == "firefox":
    if not development:
      raise ValueError("Firefox cleanup requires explicit development opt-in")
    template = json.loads((ROOT / "firefox/host-manifest.template.json").read_text(encoding="utf-8"))
    gecko = json.loads((ROOT.parent / "extensions/webextension/firefox/gecko.json").read_text(encoding="utf-8"))
    if (set(template) != {"name", "description", "path", "type", "allowed_extensions"}
        or template["name"] != HOST_NAME or template["type"] != "stdio"
        or template["path"] != "__PDF_MAGIC_NATIVE_HOST_ABSOLUTE_PATH__"
        or gecko.get("gecko", {}).get("id") != FIREFOX_DEVELOPMENT_ID
        or template["allowed_extensions"] != [FIREFOX_DEVELOPMENT_ID]):
      raise ValueError("Unreviewed Firefox development registration identity")
    return {**template, "path": str(host_path)}
  raise ValueError("Unsupported native registration browser")


def _open_registration_directory(home, relative, stack):
  # Use directory descriptors instead of resolving paths: no symlinked parent
  # may redirect cleanup into another browser profile or user's files.
  flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
  try:
    directory = os.open(home, flags)
  except OSError as exc:
    raise ValueError("Home must be an existing real directory") from exc
  stack.callback(os.close, directory)
  for part in relative.parts:
    try:
      child = os.open(part, flags, dir_fd=directory)
    except FileNotFoundError:
      return None
    except OSError as exc:
      raise ValueError("Unsafe native registration directory") from exc
    stack.callback(os.close, child)
    directory = child
  return directory


def unregister(host_path, *, browsers, home=None, platform=None,
               extension_ids=(), development=False):
  """Preflight all requested registrations, then unlink only exact owned files.

  Returns removed manifest paths. Never creates directories or deletes a
  modified, substituted, or symlinked manifest. Missing registrations are no-ops.
  """
  host = validate_original_host_path(host_path)
  home = validate_original_host_path(Path.home() if home is None else home)
  platform = sys.platform if platform is None else platform
  requested = list(browsers)
  if (not host.is_absolute() or host.is_symlink() or
      not home.is_absolute() or not requested or
      len(set(requested)) != len(requested) or
      any(browser not in (*CHROMIUM_DIRECTORIES, "firefox") for browser in requested)):
    raise ValueError("Absolute host and home paths and distinct supported browsers required")
  chromium_selected = any(browser in CHROMIUM_DIRECTORIES for browser in requested)
  if (chromium_selected and platform != "darwin") or (
      "firefox" in requested and platform not in ("darwin", "linux")):
    raise ValueError("Uninstall cleanup is not supported for this browser/platform")
  if (extension_ids and not chromium_selected) or (development and "firefox" not in requested):
    raise ValueError("Cleanup identity options do not match the selected browser")

  # Preflight each physical target once. Chrome and Opera share one directory.
  targets = {}
  for browser in requested:
    manifest = _expected_manifest(browser, host, extension_ids, development)
    expected_bytes = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    relative = (CHROMIUM_DIRECTORIES[browser] if browser in CHROMIUM_DIRECTORIES else
                FIREFOX_MAC_DIRECTORY if platform == "darwin" else FIREFOX_LINUX_DIRECTORY)
    if relative in targets:
      if targets[relative] != expected_bytes:
        raise ValueError("Conflicting identities for shared registration location")
      continue
    targets[relative] = expected_bytes

  checked = []
  with ExitStack() as stack:
    for relative, expected_bytes in targets.items():
      directory = _open_registration_directory(home, relative, stack)
      if directory is None:
        continue
      try:
        descriptor = os.open(MANIFEST_NAME,
                             os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
      except FileNotFoundError:
        continue
      except OSError as exc:
        raise ValueError("Unsafe native host registration") from exc
      stack.callback(os.close, descriptor)
      original = os.fstat(descriptor)
      if not stat.S_ISREG(original.st_mode):
        raise ValueError("Refusing non-regular native host registration")
      # Read one extra byte, so oversized and user-customized files both fail
      # without loading arbitrary data or deleting an unrelated registration.
      content = os.read(descriptor, len(expected_bytes) + 1)
      if content != expected_bytes:
        raise ValueError("Refusing to remove modified native host registration")
      checked.append((directory, original, home / relative / MANIFEST_NAME))

    # Check every target before deleting anything (including other browsers).
    for directory, original, _ in checked:
      try:
        current = os.stat(MANIFEST_NAME, dir_fd=directory, follow_symlinks=False)
      except OSError as exc:
        raise ValueError("Registration changed during uninstall") from exc
      if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (
          original.st_dev, original.st_ino, original.st_size, original.st_mtime_ns):
        raise ValueError("Registration changed during uninstall")
    removed = []
    for directory, _, path in checked:
      os.unlink(MANIFEST_NAME, dir_fd=directory)
      removed.append(path)
    return removed


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--host-path", required=True, type=Path,
                      help="exact absolute executable path recorded during installation, even if removed")
  parser.add_argument("--browser", action="append", required=True,
                      choices=(*CHROMIUM_DIRECTORIES, "firefox"))
  parser.add_argument("--extension-id", action="append", default=[],
                      help="exact originally approved Chromium-family extension ID; preserve original order")
  parser.add_argument("--development", action="store_true",
                      help="explicitly select the existing Firefox development add-on ID")
  args = parser.parse_args(argv)
  try:
    removed = unregister(args.host_path, browsers=args.browser,
                         extension_ids=args.extension_id, development=args.development)
  except (OSError, ValueError) as exc:
    parser.error(str(exc))
  for path in removed:
    print(f"Removed native host registration: {path}")
  if not removed:
    print("No matching native host registrations found")


if __name__ == "__main__":
  main()
