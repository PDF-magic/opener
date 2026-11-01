#!/usr/bin/env python3
"""Ask about preference retention before PDF Magic Opener's guided uninstall.

This helper never reads, writes, resets or removes any user preferences.
"""

import argparse
import sys


PROMPT = "Retain PDF Magic Opener preferences for a future reinstall? [Y/n] "


def main(argv=None):
  parser = argparse.ArgumentParser(
    description="Ask whether PDF Magic Opener preferences should be retained."
  )
  parser.parse_args(argv)

  print("PDF Magic preferences include your app settings and selected PDF browser.")
  print("The shared scanner, signature files and other user data are separate.")
  print("This question does not modify files or PDF application associations.")

  try:
    answer = input(PROMPT).strip().casefold()
  except (EOFError, KeyboardInterrupt):
    print("\nNo retention decision recorded; all preferences remain untouched.", file=sys.stderr)
    return 1

  if answer in ("", "y", "yes"):
    print("Decision: RETAIN preferences. Existing settings remain untouched.")
    return 0

  if answer in ("n", "no"):
    print("Decision: DO NOT RETAIN preferences. No files were removed.")
    print("After uninstall, separately review only verified PDF Magic-specific")
    print("preferences before any manual removal. Preserve shared scanner data,")
    print("customizations and backups unless separately reviewed and authorized.")
    return 0

  print("Invalid answer; choose yes or no. No retention decision recorded.", file=sys.stderr)
  return 1


if __name__ == "__main__":
  sys.exit(main())
