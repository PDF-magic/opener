"""Test-only child used to verify renderer filesystem confinement."""
import os
from pathlib import Path
import sys


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    # Python -I omits the script directory. Restore only this trusted module
    # path, not the process cwd or user PYTHONPATH.
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
    import maximum_isolated_renderer as renderer
    context = renderer._renderer_sandbox_context(Path(__file__).resolve())
    renderer.apply_renderer_sandbox(context)

    private_path, write_path = map(Path, sys.argv[1:])
    try:
        private_path.read_bytes()
    except OSError:
        read_denied = True
    else:
        read_denied = False
    try:
        write_path.write_bytes(b"forbidden")
    except OSError:
        write_denied = True
    else:
        write_denied = False
    return 0 if read_denied and write_denied else 1


if __name__ == "__main__":
    raise SystemExit(main())
