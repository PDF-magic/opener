#!/usr/bin/env python3
"""Ask about optional scan-history retention; never change application data."""

import sys


QUESTION = "Retain saved optional scan history after uninstall? [Y/n/cancel]: "


def main(stdin=None, stdout=None, stderr=None):
  stdin = sys.stdin if stdin is None else stdin
  stdout = sys.stdout if stdout is None else stdout
  stderr = sys.stderr if stderr is None else stderr

  print("Optional scan history is separate from scanner caches and logs.", file=stdout)
  print("This question does not read, export, or delete any history.", file=stdout)
  while True:
    try:
      stdout.write(QUESTION)
      stdout.flush()
      reply = stdin.readline()
    except (OSError, UnicodeError):
      print("Unable to read a choice; preserve scan history and stop uninstallation.", file=stderr)
      return 1
    if not reply:
      print("No choice received; preserve scan history and stop uninstallation.", file=stderr)
      return 1

    choice = reply.strip().lower()
    if choice in ("", "y", "yes"):
      print("Keep scan history: leave the optional history store unchanged.", file=stdout)
      return 0
    if choice in ("n", "no"):
      print("Do not retain scan history: no data has been deleted.", file=stdout)
      print("Before uninstalling, open PDF Magic Opener > Preferences > Scan History", file=stdout)
      print("and choose Clear History…, then confirm and verify the result.", file=stdout)
      print("If Scan History is unavailable or clearing fails, stop; do not delete files manually.", file=stdout)
      return 0
    if choice in ("c", "cancel", "q", "quit"):
      print("Uninstallation paused; existing scan history remains unchanged.", file=stdout)
      return 1
    print("Enter yes, no, or cancel. No data has been changed.", file=stdout)


if __name__ == "__main__":
  sys.exit(main())
