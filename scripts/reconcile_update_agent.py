#!/usr/bin/env python3
"""Leave one registered project-owned signature updater after migration.

The installer validates the existing plist using migrate_update_agent.py before
this helper is called. Only the established service label is managed: unrelated
LaunchAgents, signature data, and user settings are never touched.
"""

import os
from pathlib import Path
import subprocess
import sys

LABEL = "local.studio.pdf-malware-signatures"
AGENT_FILENAME = LABEL + ".plist"


class UpdateAgentReconciliationError(RuntimeError):
    """The updater could not be safely reconciled."""


def reconcile(home=None, uid=None, run=None):
    """Replace the loaded updater by label before registering its validated plist."""
    home = Path.home() if home is None else Path(home)
    uid = os.getuid() if uid is None else uid
    run = subprocess.run if run is None else run
    agent = home / "Library/LaunchAgents" / AGENT_FILENAME
    domain = f"gui/{uid}"
    service = f"{domain}/{LABEL}"

    def launchctl(*arguments):
        return run(
            ["launchctl", *arguments],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode

    if launchctl("print", service) == 0:
        if launchctl("bootout", service) != 0:
            raise UpdateAgentReconciliationError("Existing updater could not be stopped")
        if launchctl("print", service) == 0:
            raise UpdateAgentReconciliationError("Existing updater remains registered")
    if launchctl("bootstrap", domain, str(agent)) != 0:
        raise UpdateAgentReconciliationError("Updater could not be registered")
    if launchctl("print", service) != 0:
        raise UpdateAgentReconciliationError("Updater registration could not be verified")


def main():
    try:
        reconcile()
    except (OSError, UpdateAgentReconciliationError) as error:
        print(f"Signature-update agent reconciliation refused: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
