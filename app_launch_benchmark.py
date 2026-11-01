#!/usr/bin/env python3
"""Measure the real Debug preferences app's first SwiftUI appearance in isolation."""

import argparse
import json
import math
import os
from pathlib import Path
import plistlib
import select
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time

BUNDLE_NAME = "PDFMagicOpener.app"
BUNDLE_ID = "local.studio.pdfmagicopener.swiftui"
ERROR = "Application launch benchmark failed; no results were recorded."
TIMEOUT_SECONDS = 20


def validate_app(app):
  if (app.name != BUNDLE_NAME or app.is_symlink() or not app.is_dir()):
    raise ValueError(ERROR)
  try:
    with (app / "Contents/Info.plist").open("rb") as stream:
      info = plistlib.load(stream)
  except (OSError, ValueError, TypeError) as exc:
    raise ValueError(ERROR) from exc
  if (info.get("CFBundleIdentifier") != BUNDLE_ID
      or info.get("CFBundleExecutable") != "PDFMagicOpener"
      or info.get("CFBundlePackageType") != "APPL"
      or "CFBundleDocumentTypes" in info):
    raise ValueError(ERROR)
  executable = app / "Contents/MacOS/PDFMagicOpener"
  if executable.is_symlink() or not executable.is_file() or not os.access(executable, os.X_OK):
    raise ValueError(ERROR)
  return executable


def launch_once(executable, home, temp, *, timeout=TIMEOUT_SECONDS):
  """Time process creation through the Debug-only first-view-ready pipe marker."""
  read_fd, write_fd = os.pipe()
  process = None
  try:
    env = os.environ.copy()
    env.update({
      "HOME": str(home),
      "TMPDIR": str(temp) + os.sep,
      "XDG_CONFIG_HOME": str(home / ".config"),
      "PDFMAGIC_LAUNCH_BENCHMARK_FD": str(write_fd),
    })
    started = time.perf_counter_ns()
    process = subprocess.Popen(
      [str(executable)], cwd=str(home), env=env, pass_fds=(write_fd,),
      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL, start_new_session=True,
    )
    os.close(write_fd)
    write_fd = -1
    deadline = time.monotonic() + timeout
    while True:
      if process.poll() is not None:
        raise RuntimeError(ERROR)
      remaining = deadline - time.monotonic()
      if remaining <= 0:
        raise RuntimeError(ERROR)
      readable, _, _ = select.select([read_fd], [], [], min(0.1, remaining))
      if readable:
        result = os.read(read_fd, 1)
        finished = time.perf_counter_ns()
        if result != b"1" or process.poll() is not None:
          raise RuntimeError(ERROR)
        seconds = (finished - started) / 1_000_000_000
        if not math.isfinite(seconds) or seconds <= 0:
          raise RuntimeError(ERROR)
        return seconds
  except (OSError, subprocess.SubprocessError) as exc:
    raise RuntimeError(ERROR) from exc
  finally:
    os.close(read_fd)
    if write_fd >= 0:
      os.close(write_fd)
    if process is not None:
      # Only the process group created for this attempt can be terminated.
      if process.poll() is None:
        try:
          os.killpg(process.pid, signal.SIGTERM)
          process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
          if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
      else:
        process.wait()


def measure(app, samples=3, *, platform=sys.platform, run_attempt=launch_once):
  if platform != "darwin" or type(samples) is not int or not 3 <= samples <= 10:
    raise ValueError(ERROR)
  executable = validate_app(app)
  # Both the app bundle and HOME are disposable. Never exercise an installed
  # application or change the real user's defaults, registrations or settings.
  with tempfile.TemporaryDirectory(prefix="pdfmagic-app-launch-") as folder:
    root = Path(folder)
    portable = root / "standalone" / BUNDLE_NAME
    portable.parent.mkdir()
    shutil.copytree(app, portable, symlinks=True)
    home = root / "fresh-home"
    home.mkdir()
    temp = root / "tmp"
    temp.mkdir()
    executable = portable / "Contents/MacOS" / executable.name
    durations = []
    for index in range(samples + 1):
      duration = run_attempt(executable, home, temp)
      if (not isinstance(duration, (int, float)) or isinstance(duration, bool)
          or not math.isfinite(duration) or duration <= 0):
        raise RuntimeError(ERROR)
      if index:
        durations.append(duration)
  ordered = sorted(durations)
  return {
    "schemaVersion": 1,
    "scope": "debugPreferencesProcessToFirstSwiftUIViewAppear",
    "sampleCount": samples,
    "discardedWarmup": 1,
    "medianMs": round(statistics.median(ordered) * 1000, 3),
    "p90Ms": round(ordered[math.ceil(0.9 * samples) - 1] * 1000, 3),
  }


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--app", type=Path, required=True,
                      help="verified, staged Debug PDFMagicOpener.app on disposable macOS")
  parser.add_argument("--samples", type=int, default=3)
  args = parser.parse_args(argv)
  try:
    report = measure(args.app, args.samples)
  except (ValueError, RuntimeError, OSError, shutil.Error):
    parser.exit(1, ERROR + "\n")
  print(json.dumps(report, sort_keys=True, allow_nan=False))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
