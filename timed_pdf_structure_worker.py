"""Private, fixed-command child for timed optional PDF structure inspection.

Run by timed_pdf_structure_analysis only. The supervisor handles the deadline,
process-group cleanup and bounded stdout; this worker accepts only stdin bytes
and returns the validated metadata contract (no PDF content or diagnostics).
"""

import json
import os
import sys


def main():
  if len(sys.argv) != 1:
    return 2
  # Python -I removes the script folder from sys.path; restore only this
  # trusted repository folder, never the caller's cwd or an input PDF path.
  sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

  from pdf_structure_parser import MAX_STRUCTURE_INPUT_BYTES, parse_pdf_structure

  contents = sys.stdin.buffer.read(MAX_STRUCTURE_INPUT_BYTES + 1)
  if not 0 < len(contents) <= MAX_STRUCTURE_INPUT_BYTES:
    return 2
  report = parse_pdf_structure(contents)
  payload = report.to_dict()
  if payload.get("authorizesOpen") is not False:
    return 2
  sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
  sys.stdout.flush()
  return 0


if __name__ == "__main__":
  try:
    exit_code = main()
  except BaseException:
    # Parent always reports a fixed failure, never a parser traceback.
    exit_code = 2
  raise SystemExit(exit_code)
