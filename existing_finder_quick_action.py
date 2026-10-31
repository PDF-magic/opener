#!/usr/bin/env python3
"""Read-only migration inventory for the legacy Finder Quick Action and backup.

The installer historically uses Allow and Open.workflow and writes a
document.wflow.before-brave backup on its first update. Detection never
loads workflow contents, follows links, or changes either artifact.
"""

import argparse
import json
from pathlib import Path
import stat
from typing import Literal


ArtifactState = Literal["present", "missing", "unsafe", "unreadable"]
WORKFLOW_PARTS = (
    "Library", "Services", "Allow and Open.workflow", "Contents", "document.wflow",
)
BACKUP_PARTS = WORKFLOW_PARTS[:-1] + ("document.wflow.before-brave",)


def _artifact_state(home: Path, parts: tuple[str, ...]) -> ArtifactState:
    current = home
    for index, part in enumerate(parts):
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            return "missing"
        except OSError:
            return "unreadable"
        if stat.S_ISLNK(mode):
            return "unsafe"
        if index < len(parts) - 1:
            if not stat.S_ISDIR(mode):
                return "unsafe"
        elif not stat.S_ISREG(mode):
            return "unsafe"
    return "present"


def detect_existing_finder_quick_action(home: Path | None = None) -> dict[str, ArtifactState]:
    """Report independent existence/safety states without opening user files.

    A backup may exist even if its active workflow has been removed. "unsafe"
    means a link or an unexpected file type; "unreadable" means the state
    could not be determined and must not be treated as an absent installation.
    """
    root = Path.home() if home is None else Path(home)
    return {
        "finder_quick_action": _artifact_state(root, WORKFLOW_PARTS),
        "finder_quick_action_backup": _artifact_state(root, BACKUP_PARTS),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, help="Home directory to inspect (default: current user)")
    arguments = parser.parse_args()
    print(json.dumps(detect_existing_finder_quick_action(arguments.home), sort_keys=True))


if __name__ == "__main__":
    main()
