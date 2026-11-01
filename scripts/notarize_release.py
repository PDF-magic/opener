#!/usr/bin/env python3
"""Notarize a signed macOS app archive; publish only a stapled, verified copy.

This program never signs code, changes installed applications, or reads local
scanner signatures, preferences, or signing credential files.
"""

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import stat
import subprocess
import tempfile
import zipfile

from package_application_helpers import APP_NAME, BUNDLE_ID, validate_helpers

TEAM_ID_PATTERN = re.compile(r"[A-Z0-9]{10}\Z")
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10000


class NotarizationError(Exception):
  """An intentionally credential-free release failure message."""


def checked(args, *, timeout=120):
  """Do not echo commands, environment values, or tool output on failure."""
  try:
    result = subprocess.run(args, check=True, capture_output=True, text=True,
                            timeout=timeout)
  except (OSError, subprocess.SubprocessError) as error:
    raise NotarizationError("Required release verification or Apple tool failed") from error
  return result


def validate_zip(archive):
  if archive.is_symlink() or not archive.is_file() or archive.suffix.lower() != ".zip":
    raise NotarizationError("Expected a regular signed application ZIP archive")
  try:
    with zipfile.ZipFile(archive) as zipped:
      members = zipped.infolist()
      if not members or len(members) > MAX_ARCHIVE_ENTRIES:
        raise NotarizationError("Unexpected number of signed archive entries")
      if sum(item.file_size for item in members) > MAX_UNCOMPRESSED_BYTES:
        raise NotarizationError("Signed archive exceeds the uncompressed size limit")
      for member in members:
        name = member.filename
        path = PurePosixPath(name)
        # ditto can include Apple resource-fork metadata in __MACOSX.
        allowed = (name.startswith(APP_NAME + "/")
                   or name == "__MACOSX/"
                   or name == "__MACOSX/" + APP_NAME + "/"
                   or name == "__MACOSX/._" + APP_NAME
                   or name.startswith("__MACOSX/" + APP_NAME + "/"))
        if (not allowed or path.is_absolute()
            or ".." in path.parts or "\\" in name or "\x00" in name):
          raise NotarizationError("Signed archive contains an unexpected path")
        mode = member.external_attr >> 16
        kind = stat.S_IFMT(mode)
        if kind not in (0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK):
          raise NotarizationError("Signed archive contains an unsupported entry")
        if kind == stat.S_IFLNK:
          if not name.startswith(APP_NAME + "/"):
            raise NotarizationError("Unexpected metadata symlink")
          # A signed framework symlink may be relative but must not escape the app.
          target = zipped.read(member).decode("utf-8", errors="strict")
          parts = list(path.parts[:-1])
          if target.startswith("/"):
            raise NotarizationError("Signed archive contains an escaping symlink")
          for part in PurePosixPath(target).parts:
            if part == "..":
              if len(parts) <= 1:
                raise NotarizationError("Signed archive contains an escaping symlink")
              parts.pop()
            elif part not in ("", "."):
              parts.append(part)
          if not parts or parts[0] != APP_NAME:
            raise NotarizationError("Signed archive contains an escaping symlink")
  except (OSError, zipfile.BadZipFile, UnicodeError, RuntimeError) as error:
    raise NotarizationError("Cannot verify the signed application ZIP") from error


def verify_signed_app(app, team_id):
  try:
    validate_helpers(app)
    with (app / "Contents/Info.plist").open("rb") as stream:
      info = plistlib.load(stream)
  except (OSError, ValueError, plistlib.InvalidFileException) as error:
    raise NotarizationError("Signed application identity or helpers are invalid") from error
  if info.get("CFBundleIdentifier") != BUNDLE_ID:
    raise NotarizationError("Unexpected signed application bundle identifier")
  checked(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)])
  signature_result = checked(["codesign", "-dv", "--verbose=4", str(app)])
  signature = signature_result.stdout + "\n" + signature_result.stderr
  if (f"Identifier={BUNDLE_ID}" not in signature.splitlines()
      or f"TeamIdentifier={team_id}" not in signature.splitlines()
      or not any(line.startswith("Authority=Developer ID Application:")
                 for line in signature.splitlines())
      or not any("runtime" in line for line in signature.splitlines()
                 if line.startswith("CodeDirectory ") or line.startswith("flags="))):
    raise NotarizationError("Developer ID team, hardened runtime, or app identity mismatch")
  for name in sorted((app / "Contents/Helpers").iterdir()):
    checked(["codesign", "--verify", "--strict", "--verbose=2", str(name)])


def notary_json(args, credentials):
  raw = checked(["xcrun", "notarytool", *args, *credentials,
                 "--output-format", "json"], timeout=3600).stdout
  try:
    response = json.loads(raw)
    if not isinstance(response, dict):
      raise ValueError("Notarization status must be an object")
    return response
  except (ValueError, TypeError) as error:
    raise NotarizationError("Apple returned an invalid notarization response") from error


def notarize(signed_zip, output_zip, *, apple_id, password, team_id):
  signed_zip = Path(signed_zip).absolute()
  output_zip = Path(output_zip).absolute()
  if (not apple_id or not password or not TEAM_ID_PATTERN.fullmatch(team_id or "")):
    raise NotarizationError("Missing or invalid notarization account configuration")
  if output_zip.suffix.lower() != ".zip" or output_zip.exists() or output_zip.is_symlink():
    raise NotarizationError("Output must be a new ZIP path; refusing to overwrite")
  if not output_zip.parent.is_dir() or output_zip.parent.is_symlink():
    raise NotarizationError("Output parent must be an existing real directory")
  validate_zip(signed_zip)
  credentials = ["--apple-id", apple_id, "--password", password, "--team-id", team_id]
  with tempfile.TemporaryDirectory(prefix=".pdfmagic-notary-", dir=output_zip.parent) as temporary:
    staging = Path(temporary)
    checked(["ditto", "-x", "-k", str(signed_zip), str(staging)])
    app = staging / APP_NAME
    if app.is_symlink() or not app.is_dir():
      raise NotarizationError("Signed application is absent from the archive")
    verify_signed_app(app, team_id)
    submitted = notary_json(["submit", str(signed_zip), "--wait"], credentials)
    identifier = submitted.get("id")
    if (not isinstance(identifier, str)
        or not re.fullmatch(r"[0-9a-fA-F-]{36}", identifier)
        or submitted.get("status") != "Accepted"):
      raise NotarizationError("Apple did not accept the notarization submission")
    verified = notary_json(["info", identifier], credentials)
    if verified.get("id") != identifier or verified.get("status") != "Accepted":
      raise NotarizationError("Apple notarization status could not be independently verified")
    checked(["xcrun", "stapler", "staple", str(app)])
    checked(["xcrun", "stapler", "validate", str(app)])
    verify_signed_app(app, team_id)
    checked(["spctl", "--assess", "--type", "execute", "--verbose=4", str(app)])
    packed = staging / "verified-notarized.zip"
    checked(["ditto", "-c", "-k", "--keepParent", str(app), str(packed)])
    validate_zip(packed)
    # Exclusive creation: never replace an existing release, even in a race.
    try:
      os.link(packed, output_zip)
    except OSError as error:
      raise NotarizationError("Unable to publish a new verified notarized ZIP") from error
  return identifier


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--signed-zip", type=Path, required=True)
  parser.add_argument("--output-zip", type=Path, required=True)
  args = parser.parse_args(argv)
  try:
    identifier = notarize(args.signed_zip, args.output_zip,
                          apple_id=os.environ.get("NOTARY_APPLE_ID", ""),
                          password=os.environ.get("NOTARY_APP_PASSWORD", ""),
                          team_id=os.environ.get("NOTARY_TEAM_ID", ""))
  except NotarizationError as error:
    parser.exit(1, "Notarization blocked: " + str(error) + "\n")
  print("Apple notarization accepted and independently verified; stapled archive created.")
  print("Submission ID:", identifier)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
