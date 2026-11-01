#!/usr/bin/env python3
"""Sign and verify a staged Developer ID app, including its nested code."""
import argparse
from pathlib import Path
import plistlib
import re
import stat
import subprocess

from package_application_helpers import APP_NAME, BUNDLE_ID, HELPER_FOLDER, validate_helpers

EXTENSION = Path("Contents/PlugIns/PDFMagicOpenerSafari.appex")
ENTITLEMENTS = Path(__file__).resolve().parents[1] / "extensions/safari/SafariExtension.entitlements"
CODESIGN = "/usr/bin/codesign"
MACHO = frozenset((b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf",
                   b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xce",
                   b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
                   b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"))


def bundle_identity(bundle, identifier, executable, package_type):
  if bundle.is_symlink() or not bundle.is_dir():
    raise ValueError("Missing or unsafe nested bundle")
  info = bundle / "Contents/Info.plist"
  if info.is_symlink() or not info.is_file():
    raise ValueError("Missing bundle metadata")
  with info.open("rb") as stream:
    metadata = plistlib.load(stream)
  if (metadata.get("CFBundleIdentifier") != identifier
      or metadata.get("CFBundleExecutable") != executable
      or metadata.get("CFBundlePackageType") != package_type):
    raise ValueError("Unexpected embedded bundle identity")
  target = bundle / "Contents/MacOS" / executable
  if target.is_symlink() or not target.is_file() or not target.stat().st_mode & stat.S_IXUSR:
    raise ValueError("Missing nested executable")
  with target.open("rb") as stream:
    if stream.read(4) not in MACHO:
      raise ValueError("Nested executable is not Mach-O")


def signing_targets(app):
  app = Path(app)
  validate_helpers(app)
  if any(path.is_symlink() for path in app.rglob("*")):
    raise ValueError("Symlinks cannot enter Developer ID distribution")
  extension = app / EXTENSION
  bundle_identity(extension, BUNDLE_ID + ".safari", "PDFMagicOpenerSafari", "XPC!")
  if list(app.rglob("*.appex")) != [extension]:
    raise ValueError("Unreviewed extension bundle")
  if list(app.rglob("*.framework")) or list(app.rglob("*.xpc")):
    raise ValueError("Unreviewed nested framework or service")
  nested = sorted((path for path in app.rglob("*.app") if path != app),
                  key=lambda path: (-len(path.parts), str(path)))
  for helper in nested:
    if helper.relative_to(app).parts[:3] != ("Contents", "Library", "LoginItems"):
      raise ValueError("Unreviewed nested helper app location")
    info = helper / "Contents/Info.plist"
    if info.is_symlink() or not info.is_file():
      raise ValueError("Missing helper app metadata")
    with info.open("rb") as stream:
      metadata = plistlib.load(stream)
    identifier, executable = metadata.get("CFBundleIdentifier"), metadata.get("CFBundleExecutable")
    if (not isinstance(identifier, str) or not identifier.startswith(BUNDLE_ID + ".")
        or not isinstance(executable, str) or not executable or "/" in executable):
      raise ValueError("Unreviewed helper app identifier")
    bundle_identity(helper, identifier, executable, "APPL")
  helpers = sorted((app / HELPER_FOLDER).iterdir())
  extras = []
  for path in sorted((app / "Contents/MacOS").iterdir()):
    if path.name == "PDFMagicOpener":
      continue
    if not path.is_file() or not path.stat().st_mode & stat.S_IXUSR:
      raise ValueError("Unreviewed host executable")
    with path.open("rb") as stream:
      if stream.read(4) not in MACHO:
        raise ValueError("Unreviewed non-Mach-O host executable")
    extras.append(path)
  targets = [*helpers, *extras, *nested, extension, app]
  for path in app.rglob("*"):
    if path == app / "Contents/MacOS/PDFMagicOpener":
      continue
    if (path.is_file() and path.stat().st_mode & stat.S_IXUSR
        and not any(path == item or (item != app and item in path.parents)
                    for item in targets)):
      raise ValueError("Unreviewed executable in distribution app")
  return targets


def codesign(*args):
  return subprocess.run([CODESIGN, *map(str, args)], check=True,
                        capture_output=True, text=True, timeout=120)


def verify(app, team_id):
  if not re.fullmatch(r"[A-Z0-9]{10}", team_id):
    raise ValueError("Invalid Apple team ID")
  targets = signing_targets(app)
  for target in targets:
    codesign("--verify", "--strict", "--verbose=2", target)
    details = codesign("--display", "--verbose=4", target)
    lines = (details.stdout + "\n" + details.stderr).splitlines()
    if (f"TeamIdentifier={team_id}" not in lines
        or not any(line.startswith("Authority=Developer ID Application: ") for line in lines)
        or not any(line.startswith("CodeDirectory ") and "runtime" in line for line in lines)):
      raise ValueError("Missing hardened Developer ID signature on " + str(target))
  return targets


def sign(app, team_id, identity):
  if not re.fullmatch(r"[A-Z0-9]{10}", team_id):
    raise ValueError("Invalid Apple team ID")
  named = re.fullmatch(r"Developer ID Application: .+ \(([A-Z0-9]{10})\)", identity)
  if not ((named and named.group(1) == team_id)
          or re.fullmatch(r"[0-9a-fA-F]{40}", identity)):
    raise ValueError("Expected matching Developer ID Application identity or certificate SHA-1")
  targets = signing_targets(app)
  for target in targets:
    options = ["--force", "--sign", identity, "--options", "runtime", "--timestamp"]
    if target == Path(app) / EXTENSION:
      options.extend(("--entitlements", ENTITLEMENTS))
    codesign(*options, target)
  return verify(app, team_id)


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--app", required=True, type=Path)
  parser.add_argument("--team-id", required=True)
  mode = parser.add_mutually_exclusive_group(required=True)
  mode.add_argument("--sign")
  mode.add_argument("--verify-only", action="store_true")
  args = parser.parse_args()
  try:
    targets = (sign(args.app, args.team_id, args.sign)
               if args.sign else verify(args.app, args.team_id))
  except (ValueError, OSError, subprocess.SubprocessError) as error:
    # Never echo keychain or subprocess output into public logs.
    parser.exit(1, f"Developer ID signature verification failed: {type(error).__name__}\n")
  print("Verified Developer ID signatures on", len(targets), "code objects")


if __name__ == "__main__":
  main()
