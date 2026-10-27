#!/bin/bash
# Both Finder entry points and the native PDF app share this scan gate.
# The native PDF app supplies its own scan entry-point label through the child environment.
# Preserve positional arguments: the first argument remains the document path.
export PDF_MAGIC_REQUESTING_APPLICATION="${PDF_MAGIC_REQUESTING_APPLICATION:-Allow and Open}"
script_dir="$(cd "$(dirname "$0")" && pwd)"
/usr/bin/python3 "$script_dir/record-scan-origin.py" "$@" >/dev/null 2>&1 || true
exec /usr/bin/python3 "$script_dir/scan-and-open.py" "$@"
