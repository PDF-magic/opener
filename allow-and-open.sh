#!/bin/bash
# Both Finder entry points and the native PDF app share this scan gate.
# This labels the scanner entry point, not an external Launch Services caller.
if [[ "${1-}" == "--from-pdf-magic-opener" ]]; then
    shift
    export PDF_MAGIC_REQUESTING_APPLICATION="PDF Magic Opener"
else
    export PDF_MAGIC_REQUESTING_APPLICATION="Allow and Open"
fi
script_dir="$(cd "$(dirname "$0")" && pwd)"
exec /usr/bin/python3 "$script_dir/scan-and-open.py" "$@"
