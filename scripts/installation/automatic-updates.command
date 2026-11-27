#!/bin/bash
# Double-click from a complete, trusted PDF Magic Opener checkout.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 -I "$directory/repository-updates.py"
