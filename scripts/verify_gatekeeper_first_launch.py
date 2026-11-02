#!/usr/bin/env python3
"""Fail-closed first Launch Services open of a quarantined notarized macOS app."""
import argparse
import os
from pathlib import Path
import plistlib
import re
import signal
import subprocess
import sys
import tempfile
import time

APP_NAME = "PDFMagicOpener.app"
EXECUTABLE = "PDFMagicOpener"
BUNDLE_ID = "local.studio.pdfmagicopener.swiftui"
QUARANTINE = "com.apple.quarantine"
MARKER = b"0083;00000000;Safari;00000000-0000-0000-0000-000000000000"
ROOT = Path(__file__).resolve().parents[1]


class FirstLaunchError(Exception):
  """Release verification failed without exposing sensitive tool output."""


def gatekeeper_enabled(result):
  lines = (result.stdout + "\n" + result.stderr).lower().splitlines()
  if result.returncode != 0 or [s.strip() for s in lines].count("assessments enabled") != 1:
    raise FirstLaunchError("Gatekeeper must report assessments enabled")


def notarized_acceptance(result):
  lines = [s.strip().lower() for s in (result.stdout + "\n" + result.stderr).splitlines()]
  if (result.returncode != 0
      or not any(re.search(r":\s*accepted$", s) for s in lines)
      or "source=notarized developer id" not in lines):
    raise FirstLaunchError("Gatekeeper did not accept the notarized Developer ID app")


def checked(args, *, timeout=60):
  try:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
  except (OSError, subprocess.SubprocessError) as error:
    raise FirstLaunchError("Required macOS verification tool failed") from error
  if result.returncode != 0:
    raise FirstLaunchError("Required macOS verification command failed")
  return result


def app_pids():
  try:
    result = subprocess.run(
      ["/usr/bin/pgrep", "-x", EXECUTABLE],
      capture_output=True, text=True, timeout=10,
    )
  except (OSError, subprocess.SubprocessError) as error:
    raise FirstLaunchError("Cannot inspect running app processes") from error
  if result.returncode == 1 and not result.stdout.strip():
    return set()
  if result.returncode != 0:
    raise FirstLaunchError("Cannot reliably inspect running app processes")
  try:
    pids = {int(item) for item in result.stdout.split()}
  except ValueError as error:
    raise FirstLaunchError("Unexpected process identifiers") from error
  if not pids or any(pid <= 1 for pid in pids):
    raise FirstLaunchError("Unexpected running app process list")
  return pids


def confirm_fresh_launch(app):
  """Use Launch Services rather than bypassing Gatekeeper via direct exec."""
  if app_pids():
    raise FirstLaunchError("An existing app process invalidates first launch")
  try:
    opener = subprocess.Popen(
      ["/usr/bin/open", "-n", "-W", "-a", str(app)],
      stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
  except OSError as error:
    raise FirstLaunchError("Launch Services could not start") from error
  launched = set()
  try:
    for _ in range(30):
      if opener.poll() is not None:
        raise FirstLaunchError("Launch Services exited before the app started")
      launched = app_pids()
      if launched:
        time.sleep(5)
        if not (launched & app_pids()):
          raise FirstLaunchError("The first-launched app did not remain running")
        if opener.poll() is not None:
          raise FirstLaunchError("Launch Services did not retain the app session")
        return
      time.sleep(1)
    raise FirstLaunchError("No first-launch process appeared within 30 seconds")
  finally:
    # Only stop processes that appeared after the clean-runner baseline check.
    if launched:
      for pid in launched & app_pids():
        try:
          os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
          pass
    if opener.poll() is None:
      opener.terminate()
    try:
      opener.communicate(timeout=10)
    except subprocess.TimeoutExpired:
      opener.kill()
      opener.communicate(timeout=5)


def verify(app, team_id):
  if sys.platform != "darwin":
    raise FirstLaunchError("A real macOS runner is required")
  if not re.fullmatch(r"[A-Z0-9]{10}", team_id):
    raise FirstLaunchError("A ten-character Developer ID team ID is required")
  app = app.absolute()
  allowed = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())).resolve()
  if (app.is_symlink() or not app.is_dir() or app.name != APP_NAME
      or not app.resolve().is_relative_to(allowed) or app.resolve() == allowed):
    raise FirstLaunchError("App must be a real bundle in disposable runner storage")
  try:
    with (app / "Contents" / "Info.plist").open("rb") as stream:
      info = plistlib.load(stream)
  except (OSError, ValueError) as error:
    raise FirstLaunchError("Cannot verify app identity") from error
  if (info.get("CFBundleIdentifier") != BUNDLE_ID
      or info.get("CFBundleExecutable") != EXECUTABLE
      or info.get("CFBundlePackageType") != "APPL"
      or "CFBundleDocumentTypes" in info):
    raise FirstLaunchError("Unexpected app identity or PDF handler registration")
  if not (app / "Contents" / "MacOS" / EXECUTABLE).is_file():
    raise FirstLaunchError("Application executable is missing")
  # Existing verifier checks Developer ID, team, hardened runtime and helpers.
  checked([sys.executable, str(ROOT / "scripts" / "sign_developer_id.py"),
           "--app", str(app), "--team-id", team_id, "--verify-only"])
  checked(["/usr/bin/xcrun", "stapler", "validate", str(app)])
  gatekeeper_enabled(checked(["/usr/sbin/spctl", "--status"]))
  if app_pids():
    raise FirstLaunchError("A prior launch invalidates this check")
  # Tag only the extracted, disposable bundle; never remove quarantine.
  checked(["/usr/bin/xattr", "-wx", QUARANTINE, MARKER.hex(), str(app)])
  quarantine = checked(["/usr/bin/xattr", "-px", QUARANTINE, str(app)])
  if bytes.fromhex(quarantine.stdout.strip()) != MARKER:
    raise FirstLaunchError("Download quarantine was not retained")
  assessment = subprocess.run(
    ["/usr/sbin/spctl", "--assess", "--type", "execute", "--verbose=4",
     "--no-cache", str(app)],
    capture_output=True, text=True, timeout=60,
  )
  notarized_acceptance(assessment)
  quarantine = checked(["/usr/bin/xattr", "-px", QUARANTINE, str(app)])
  if bytes.fromhex(quarantine.stdout.strip()) != MARKER:
    raise FirstLaunchError("Assessment altered the quarantine marker")
  confirm_fresh_launch(app)
  gatekeeper_enabled(checked(["/usr/sbin/spctl", "--status"]))
  print("PASS: Gatekeeper-enabled first Launch Services open of notarized app")


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--app", type=Path, required=True)
  parser.add_argument("--team-id", required=True)
  args = parser.parse_args()
  try:
    verify(args.app, args.team_id)
  except (FirstLaunchError, OSError, subprocess.SubprocessError, ValueError) as error:
    parser.exit(1, "Gatekeeper first-launch verification blocked: " + str(error) + "\n")


if __name__ == "__main__":
  main()
