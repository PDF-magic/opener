#!/usr/bin/env python3
"""Verify macOS Release app and Safari extension signatures without using signing secrets.

The check inspects built code, not just project settings. It never installs,
launches, registers, or modifies the app or the system's PDF handler.
"""
import argparse
from pathlib import Path
import plistlib
import re
import subprocess
import sys

HOST_ID = "local.studio.pdfmagicopener.swiftui"
SAFARI_ID = HOST_ID + ".safari"
RUNTIME_FLAG = 0x10000  # CS_RUNTIME: hardened runtime
EXPECTED = (
  ("host", Path("."), HOST_ID, {}),
  ("Safari", Path("Contents/PlugIns/PDFMagicOpenerSafari.appex"),
   SAFARI_ID, {"com.apple.security.app-sandbox": True}),
)


def run_codesign(*arguments):
  return subprocess.run(
    ["/usr/bin/codesign", *arguments], capture_output=True, check=False)


def verify_runtime_flags(details):
  match = re.search(r"flags=0x([0-9a-fA-F]+)", details)
  if not match or not (int(match.group(1), 16) & RUNTIME_FLAG):
    raise ValueError("Missing hardened runtime (CS_RUNTIME) signature flag")


def verify_entitlements(actual, expected):
  if actual != expected:
    raise ValueError("Unexpected signed entitlements: " + repr(actual))


def verify_component(path, bundle_id, expected_entitlements):
  if path.is_symlink() or not path.is_dir():
    raise ValueError("Missing or unsafe signed bundle: " + str(path))
  with (path / "Contents/Info.plist").open("rb") as handle:
    info = plistlib.load(handle)
  if info.get("CFBundleIdentifier") != bundle_id:
    raise ValueError("Unexpected signed bundle identifier: " + str(path))
  valid = run_codesign("--verify", "--strict", "--verbose=2", str(path))
  if valid.returncode:
    raise ValueError("Invalid macOS code signature: " + str(path))
  details = run_codesign("--display", "--verbose=4", str(path))
  if details.returncode:
    raise ValueError("Cannot read signed runtime flags: " + str(path))
  verify_runtime_flags(details.stderr.decode("utf-8", errors="replace"))

  rights = run_codesign("--display", "--entitlements", ":-", str(path))
  if rights.returncode and not (
      expected_entitlements == {}
      and not rights.stdout.strip()
      and b"entitlement" in rights.stderr.lower()):
    raise ValueError("Cannot read signed entitlements: " + str(path))
  try:
    actual = plistlib.loads(rights.stdout) if rights.stdout.strip() else {}
  except (ValueError, TypeError, plistlib.InvalidFileException) as error:
    raise ValueError("Malformed signed entitlements: " + str(path)) from error
  verify_entitlements(actual, expected_entitlements)


def verify_app(app):
  if app.name != "PDFMagicOpener.app":
    raise ValueError("Expected built PDFMagicOpener.app")
  for name, relative, bundle_id, expected in EXPECTED:
    try:
      verify_component(app / relative, bundle_id, expected)
    except (OSError, ValueError) as error:
      raise ValueError(name + " signing verification failed: " + str(error)) from error


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--app", type=Path, required=True)
  args = parser.parse_args()
  if sys.platform != "darwin":
    parser.error("Signed bundle inspection requires macOS codesign")
  try:
    verify_app(args.app)
  except ValueError as error:
    parser.exit(1, str(error) + "\n")
  print("Verified signed host and Safari extension: hardened runtime and exact entitlements")


if __name__ == "__main__":
  main()
