#!/bin/bash
# Finder/Terminal "Repair Installation" action. Run only from a complete,
# trusted PDF Magic Opener source checkout; never escalate privileges.
set -euo pipefail

if [ "$EUID" -eq 0 ]; then
    echo "Repair Installation must run as your normal user, never with sudo." >&2
    exit 1
fi

# Resolve the location independently of the current working directory.
# Refuse links so a renamed, replaced or redirected launcher is not followed.
if [ -L "${BASH_SOURCE[0]}" ]; then
    echo "Unsafe Repair Installation action; use the original source checkout." >&2
    exit 1
fi
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
installer="$script_dir/install-allow-and-open.sh"
if [ -L "$installer" ] || [ ! -f "$installer" ] || [ ! -r "$installer" ] ||
   [ ! -f "$script_dir/scripts/report_install_prerequisites.py" ] ||
   [ ! -f "$script_dir/scripts/confirm_clamav_install.py" ]; then
    echo "Repair source is incomplete or unsafe. Use a complete PDF Magic Opener checkout." >&2
    exit 1
fi

# No argument, environment, piped stdin, or unattended invocation may waive
# the confirmation. /dev/tty must be an actual controlling terminal.
if [ "$#" -ne 0 ]; then
    echo "Repair Installation takes no options. Run it interactively." >&2
    exit 1
fi

if ! {
    printf '\nRepair Installation will rerun the existing PDF Magic Opener installer.\n' > /dev/tty &&
    printf 'It may rebuild and replace managed application helpers and update malware definitions.\n' > /dev/tty &&
    printf 'Existing user browser choices, custom Finder workflows and update settings are preserved.\n' > /dev/tty &&
    printf 'Missing ClamAV requires a separate installation approval. No sudo is performed.\n' > /dev/tty &&
    printf 'Type REPAIR and press Return to proceed (anything else cancels): ' > /dev/tty &&
    IFS= read -r response < /dev/tty
}; then
    echo "Repair cancelled: an interactive controlling terminal is required." >&2
    exit 1
fi

if [ "$response" != "REPAIR" ]; then
    echo "Repair cancelled; installation was not changed." >&2
    exit 1
fi

# Reuse every established migration, consent, backup, integrity and scan gate.
# Do not duplicate installer logic, invoke a package manager, or edit settings.
exec /bin/bash "$installer"
