#!/usr/bin/env python3
"""Verify a notarized app installed for the first time on a disposable macOS runner.

Never execute on a developer's Mac, replace an existing app, install the PDF
scan handler, or read user preferences. The runner is discarded after the job.
This is not a substitute for acceptance on a separately provisioned clean Mac.
"""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from notarize_release import APP_NAME, NotarizationError, validate_zip, verify_signed_app

INSTALL_TARGET = Path("/Applications") / APP_NAME
TEAM_ID_PATTERN = re.compile(r"[A-Z0-9]{10}\Z")


class CleanInstallError(Exception):
  """Fail without exposing tool output or user paths."""


def require_disposable_runner(env, platform):
  expected = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_EVENT_NAME": "workflow_dispatch",
    "GITHUB_REPOSITORY": "PDF-magic/opener",
    "GITHUB_REF": "refs/heads/main",
    "RUNNER_OS": "macOS",
    "RUNNER_ENVIRONMENT": "github-hosted",
  }
  if platform != "darwin" or any(env.get(key) != value for key, value in expected.items()):
    raise CleanInstallError("Installation is restricted to a hosted macOS main-branch dispatch")
  temporary = Path(env.get("RUNNER_TEMP", ""))
  if not temporary.is_absolute() or temporary.is_symlink() or not temporary.is_dir():
    raise CleanInstallError("Missing isolated runner temporary directory")
  return temporary


def require_new_install(target):
  if target.exists() or target.is_symlink():
    raise CleanInstallError("An existing application must never be replaced")
  if target.name != APP_NAME or target.parent.is_symlink() or not target.parent.is_dir():
    raise CleanInstallError("Unexpected or unsafe installation destination")


def run_command(args, *, timeout=120):
  try:
    subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout)
  except (OSError, subprocess.SubprocessError) as error:
    raise CleanInstallError("A required macOS installation verification command failed") from error


def verify_trusted_app(app, team_id):
  try:
    verify_signed_app(app, team_id)
  except (NotarizationError, OSError, ValueError) as error:
    raise CleanInstallError("Application signature, identity or helper verification failed") from error
  run_command(["xcrun", "stapler", "validate", str(app)])
  run_command(["spctl", "--assess", "--type", "execute", "--verbose=4", str(app)])


def launch_installed_app(app, fresh_home):
  executable = app / "Contents/MacOS/PDFMagicOpener"
  if executable.is_symlink() or not executable.is_file() or not os.access(executable, os.X_OK):
    raise CleanInstallError("Installed application executable is missing")
  fresh_home.mkdir(mode=0o700)
  temp = fresh_home / "tmp"
  temp.mkdir(mode=0o700)
  env = os.environ.copy()
  env["HOME"] = str(fresh_home)
  env["TMPDIR"] = str(temp) + os.sep
  env["XDG_CONFIG_HOME"] = str(fresh_home / ".config")
  try:
    process = subprocess.Popen(
      [str(executable)], cwd=fresh_home, env=env, stdin=subprocess.DEVNULL,
      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
  except OSError as error:
    raise CleanInstallError("Installed application could not launch") from error
  try:
    time.sleep(5)
    if process.poll() is not None:
      raise CleanInstallError("Installed application terminated during first launch")
  finally:
    if process.poll() is None:
      process.terminate()
      try:
        process.wait(timeout=8)
      except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def verify_clean_install(archive, team_id, runner_temp, *, target=INSTALL_TARGET):
  if not TEAM_ID_PATTERN.fullmatch(team_id):
    raise CleanInstallError("Expected a valid Developer ID team identifier")
  archive = Path(archive)
  if archive.is_symlink() or not archive.is_file() or archive.suffix.lower() != ".zip":
    raise CleanInstallError("Expected a regular notarized application ZIP")
  require_new_install(target)
  try:
    validate_zip(archive)
  except NotarizationError as error:
    raise CleanInstallError("Notarized archive failed structural safety checks") from error
  with tempfile.TemporaryDirectory(prefix="pdfmagic-clean-install-", dir=runner_temp) as root_name:
    root = Path(root_name)
    extracted = root / "extracted"
    extracted.mkdir()
    run_command(["ditto", "-x", "-k", str(archive), str(extracted)])
    candidate = extracted / APP_NAME
    if candidate.is_symlink() or not candidate.is_dir():
      raise CleanInstallError("Notarized application is absent from archive")
    verify_trusted_app(candidate, team_id)
    require_new_install(target)
    # Only the single known bundle destination on an ephemeral hosted runner.
    # No scanner installation, PDF association or user preference migration.
    run_command(["sudo", "/usr/bin/ditto", str(candidate), str(target)])
    if target.is_symlink() or not target.is_dir():
      raise CleanInstallError("Installed application is absent or unsafe")
    run_command(["sudo", "/usr/bin/xattr", "-w", "com.apple.quarantine",
                 "0081;00000000;GitHubActions;", str(target)])
    verify_trusted_app(target, team_id)
    launch_installed_app(target, root / "fresh-home")
  print("Fresh hosted macOS installation, Gatekeeper and first launch: PASS")


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--archive", type=Path, required=True)
  parser.add_argument("--team-id", required=True)
  args = parser.parse_args(argv)
  try:
    runner_temp = require_disposable_runner(os.environ, sys.platform)
    verify_clean_install(args.archive, args.team_id, runner_temp)
  except CleanInstallError as error:
    parser.exit(1, "Clean macOS installation blocked: " + str(error) + "\n")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
