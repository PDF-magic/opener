#!/bin/bash
# Both Finder entry points and the native PDF app share this scan gate.
script_dir="$(cd "$(dirname "$0")" && pwd)"
/usr/bin/python3 "$script_dir/record-scan-origin.py" "$@" >/dev/null 2>&1 || true
exec /usr/bin/python3 "$script_dir/scan-and-open.py" "$@"
