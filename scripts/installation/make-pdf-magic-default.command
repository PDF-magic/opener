#!/bin/bash
set -euo pipefail

# Finder action: run only on explicit user request, never on PDF open.
helper="$HOME/Applications/PDF Magic Opener.app/Contents/MacOS/MakePDFMagicDefault"
if [ ! -x "$helper" ]; then
    printf '%s\n' 'PDF Magic Opener is not installed correctly. Reinstall it before using this action.' >&2
    exit 1
fi
exec "$helper"
