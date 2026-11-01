#!/usr/bin/env python3
"""Read-only, fail-closed identity check before manually uninstalling the PDF handler.

This is not a deletion tool. A matching name alone never establishes ownership.
"""
import argparse
import os
from pathlib import Path
import pwd
import stat

from verify_pdf_opener_bundle import verify_bundle


APP_NAME = "PDF Magic Opener.app"


def _directory(path: Path, uid: int) -> None:
  details = path.lstat()
  if (not stat.S_ISDIR(details.st_mode) or details.st_uid != uid or
      details.st_mode & stat.S_IWOTH):
    raise ValueError("Unrecognized, unsafe, or unowned uninstall directory: " + str(path))


def verify_installed_app(home: Path, *, uid: int | None = None) -> bool:
  """Inspect only ~/Applications/PDF Magic Opener.app; return False if absent.

  No files, applications, associations, or preferences are ever modified.
  """
  home = Path(home)
  uid = os.getuid() if uid is None else uid
  if not home.is_absolute() or ".." in home.parts:
    raise ValueError("Home must be an absolute, unambiguous path")
  applications = home / "Applications"
  app = applications / APP_NAME
  _directory(home, uid)
  _directory(applications, uid)
  try:
    details = app.lstat()
  except FileNotFoundError:
    return False
  if not stat.S_ISDIR(details.st_mode) or details.st_uid != uid:
    raise ValueError("Refusing an unrecognized or unowned application bundle")
  if details.st_mode & stat.S_IWOTH:
    raise ValueError("Refusing a world-writable application bundle")

  # Reuse the installation's exhaustive bundle inventory and exact native
  # PDF-handler metadata check; unknown files or customizations cause refusal.
  verify_bundle(app)
  for entry in app.rglob("*"):
    details = entry.lstat()
    if details.st_uid != uid:
      raise ValueError("Refusing files belonging to another owner: " + str(entry))
    if stat.S_ISREG(details.st_mode) and details.st_nlink != 1:
      raise ValueError("Refusing multiply linked application files: " + str(entry))
  return True


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  args = parser.parse_args()
  if os.geteuid() == 0 or os.getuid() == 0:
    parser.exit(1, "Run as the installing user, never as root.\n")
  home = Path.home()
  if home != Path(pwd.getpwuid(os.getuid()).pw_dir):
    parser.exit(1, "The current HOME differs from the account home; refusing.\n")
  try:
    present = verify_installed_app(home)
  except (OSError, ValueError) as error:
    parser.exit(1, f"Application ownership not verified: {error}\n")
  if not present:
    print("PDF Magic Opener.app is absent; no application removal needed.")
    return 0
  print("Verified the exact per-user PDF Magic scan-handler bundle.")
  print("Read-only check: no files removed. Recheck in Finder before moving only this app to Trash.")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
