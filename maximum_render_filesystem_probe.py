"""Test-only child used to verify renderer filesystem confinement."""
from pathlib import Path
import sys


def main() -> int:
    if len(sys.argv) != 3:
        return 2
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
