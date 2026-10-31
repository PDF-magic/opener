#!/usr/bin/env python3
"""Smoke-test a staged macOS preferences app without installing it.

Run only on a disposable macOS CI runner with a GUI session. This is a
standalone app launch test; it never registers a PDF handler or scans a file.
"""

import argparse
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time


BUNDLE_NAME = "PDFMagicOpener.app"
BUNDLE_ID = "local.studio.pdfmagicopener.swiftui"


def smoke_test(staged_app):
  if sys.platform != "darwin":
    raise RuntimeError("First-launch smoke test requires a macOS runner")

  if staged_app.is_symlink() or not staged_app.is_dir() or staged_app.name != BUNDLE_NAME:
    raise ValueError("Expected a real staged PDFMagicOpener.app")

  with (staged_app / "Contents/Info.plist").open("rb") as stream:
    info = plistlib.load(stream)
  if (info.get("CFBundleIdentifier") != BUNDLE_ID
      or info.get("CFBundleExecutable") != "PDFMagicOpener"
      or info.get("CFBundlePackageType") != "APPL"
      or "CFBundleDocumentTypes" in info):
    raise ValueError("Unexpected preferences app identity or PDF registration")

  # Copy to a separate, uninstalled location. The synthetic HOME starts
  # empty, including no app installation or existing preference files.
  # This is not a substitute for a separate macOS OS-account test.
  with tempfile.TemporaryDirectory(prefix="pdfmagic-first-launch-") as root_name:
    root = Path(root_name)
    home = root / "fresh-home"
    home.mkdir()
    temp = root / "tmp"
    temp.mkdir()
    portable = root / "standalone" / BUNDLE_NAME
    portable.parent.mkdir()
    shutil.copytree(staged_app, portable, symlinks=True)
    if (home / "Applications" / BUNDLE_NAME).exists():
      raise AssertionError("Test home unexpectedly contains an installed app")

    executable = portable / "Contents/MacOS/PDFMagicOpener"
    if not executable.is_file() or not os.access(executable, os.X_OK):
      raise ValueError("Staged app has no executable entry point")

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["TMPDIR"] = str(temp) + os.sep
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    # Launch the *actual* SwiftUI app from the staged bundle rather than
    # checking only a plist, mocking the process, or invoking the installer.
    process = subprocess.Popen(
      [str(executable)],
      cwd=root,
      env=env,
      stdin=subprocess.DEVNULL,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.PIPE,
    )
    try:
      # A missing dependency or an early SwiftUI/AppKit startup crash normally
      # terminates the process; the windowed preferences app must stay alive.
      time.sleep(5)
      if process.poll() is not None:
        stderr = process.communicate(timeout=2)[1].decode("utf-8", "replace")
        raise AssertionError(
          f"Uninstalled app exited during first launch (code {process.returncode}): "
          + stderr[-2000:])
      print("Fresh-location macOS application launch passed")
    finally:
      if process.poll() is None:
        process.terminate()
        try:
          process.communicate(timeout=8)
        except subprocess.TimeoutExpired:
          process.kill()
          process.communicate(timeout=5)
      elif process.stderr is not None:
        process.stderr.close()


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--app", type=Path, required=True,
                      help="Unsigned, verified and staged PDFMagicOpener.app")
  args = parser.parse_args()
  smoke_test(args.app)
