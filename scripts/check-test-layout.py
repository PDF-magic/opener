#!/usr/bin/env python3
"""Ensure root test files are organized without duplicate folder prefixes."""

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
MAPPING = json.loads((ROOT / "tests" / "manifest.json").read_text())
assert len(MAPPING) == len(set(MAPPING.values())), "Duplicate organized test names"
assert len(MAPPING) >= 250, "Unexpected loss of the established Python test suites"
for old, new in MAPPING.items():
    assert re.fullmatch(r"test[-_][a-z0-9_-]+\.py", old), old
    assert re.fullmatch(r"tests/[a-z-]+/[a-z0-9]+(?:-[a-z0-9]+)*\.py", new), new
    folder, filename = new.split("/")[1:]
    assert not filename.startswith(folder + "-"), new
    assert not (ROOT / old).exists(), f"Unorganized test in repository root: {old}"
    assert (ROOT / new).is_file(), f"Missing moved test: {new}"
print(f"Validated {len(MAPPING)} categorized Python tests.")
