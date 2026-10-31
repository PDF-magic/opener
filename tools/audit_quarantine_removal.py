#!/usr/bin/env python3
"""Read-only inventory of tracked source paths capable of removing macOS quarantine."""

import ast
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_EXTENSIONS = frozenset({
    ".py", ".swift", ".sh", ".command", ".applescript",
    ".mjs", ".js", ".c", ".h", ".m", ".mm", ".yml", ".yaml",
    ".pbxproj", ".plist"
})
SELF = "tools/audit_quarantine_removal.py"
LEGACY = "scan-and-open.py"
DIRECT = re.compile(
    r"\b(?:[fl]?removexattr|remove_?xattr|delete_?xattr|clear_?xattr)\b"
    r"|\bxattr\.remove\s*\(", re.IGNORECASE
)
CLI = re.compile(
    r"\b(?:/usr/bin/)?xattr\b[\s\S]{0,180}?"
    r"(?:--(?:delete|clear)\b|-([a-z]*[cd][a-z]*)\b)", re.IGNORECASE
)
RESOURCE_KEY = re.compile(
    r"\b(?:quarantinePropertiesKey|NSURLQuarantinePropertiesKey|"
    r"kLSItemQuarantineProperties)\b", re.IGNORECASE
)
RESOURCE_WRITE = re.compile(
    r"\b(?:setResourceValue|setResourceValues|LSSetItemAttribute|"
    r"LSSetItemInfoFlags)\b", re.IGNORECASE
)


def runtime_path(path):
    """Only read tracked runtime source, not private data, tests or audit fixtures."""
    p = Path(path)
    parts = [part.lower() for part in p.parts]
    if path == SELF or p.suffix.lower() not in SOURCE_EXTENSIONS:
        return False
    if any(part in {"tests", "test", "fixtures", "__pycache__", "secrets", ".git"}
           for part in parts):
        return False
    if p.name.startswith(("test-", "test_")) or p.name.endswith((".test.mjs", ".test.js")):
        return False
    if any(marker in p.name.lower() for marker in
           (".env", ".pem", "private-key", "credential", "secret", "token")):
        return False
    return True


def suspect_calls(source):
    """Conservatively locate removal APIs, destructive xattr and OS resource writes."""
    found = set()
    for pattern, label in ((DIRECT, "extended-attribute removal API"),
                           (CLI, "destructive xattr command")):
        for match in pattern.finditer(source):
            found.add((source.count("\n", 0, match.start()) + 1, label))
    for match in RESOURCE_KEY.finditer(source):
        surrounding = source[max(0, match.start() - 150):match.end() + 150]
        if RESOURCE_WRITE.search(surrounding):
            found.add((source.count("\n", 0, match.start()) + 1,
                       "possible macOS quarantine resource write"))
    return sorted(found)


def legacy_hook(source):
    """Prove the single historical remove_quarantine hook has no side effects."""
    tree = ast.parse(source, filename=LEGACY)
    defs = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "remove_quarantine"]
    if len(defs) != 1:
        raise AssertionError("Expected one legacy remove_quarantine definition")
    hook = defs[0]
    statements = [node for node in hook.body if not
                  (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                   and isinstance(node.value.value, str))]
    if not (len(statements) == 1 and isinstance(statements[0], ast.Return)
            and (statements[0].value is None or
                 (isinstance(statements[0].value, ast.Constant)
                  and statements[0].value.value is None))):
        raise AssertionError("Legacy quarantine hook must remain a no-op")
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == "remove_quarantine"]
    if len(calls) != 1:
        raise AssertionError("Expected one known legacy hook invocation")
    return {"definition_line": hook.lineno, "call_line": calls[0].lineno,
            "effect": "none; returns None"}


def inventory(root=ROOT):
    listing = subprocess.run(["git", "ls-files", "-z", "--cached"], cwd=root,
                             capture_output=True, check=True)
    paths = [raw.decode("utf-8") for raw in listing.stdout.split(b"\0") if raw]
    files = [path for path in paths if runtime_path(path)]
    findings = []
    for path in files:
        source = (root / path).read_text(encoding="utf-8", errors="replace")
        for line, kind in suspect_calls(source):
            findings.append({"path": path, "line": line, "kind": kind})
    hook = legacy_hook((root / LEGACY).read_text(encoding="utf-8"))
    return {"scanned_runtime_files": len(files), "removal_candidates": findings,
            "legacy_hook": {"path": LEGACY, **hook}}


def main():
    report = inventory()
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["removal_candidates"]:
        raise SystemExit("Quarantine removal candidate found; review before merge")


if __name__ == "__main__":
    main()
