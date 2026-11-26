"""Prepare a candidate Python filename migration without pushing changes."""
import ast
import base64
import json
import pathlib
import re
import subprocess
import sys
import zlib

files = [pathlib.Path(p.decode()) for p in subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0") if p]
skip = {pathlib.Path("scripts/prepare-python-filenames.py"), pathlib.Path(".github/workflows/audit-python-filenames.yml")}
moves = {p: p.with_name(p.name.replace("_", "-")) for p in files
         if p.suffix == ".py" and "_" in p.stem and p.name != "__init__.py"}
names = {p.stem: p for p in moves}
assert len(names) == len(moves)
assert all(not dest.exists() for dest in moves.values())
pattern = re.compile(r"(?<![\w.-])(" + "|".join(map(re.escape, sorted(p.name for p in moves))) + r")(?![\w-])")
alternatives = "|".join(map(re.escape, sorted(names)))
module_names = re.compile(r"(?:^|\.)(?:" + alternatives + r")$")
import_line = re.compile(r"(?m)^([ \t]*)(?=(?:from[ \t]+(?:[\w.]+\.)?(?:" + alternatives +
                         r")[ \t]+import\b|import[ \t]+(?:[\w.]+\.)?(?:" + alternatives + r")\b))")
mapping = {}
for old, new in moves.items():
    for name in (old.stem, ".".join(old.with_suffix("").parts)):
        assert name not in mapping or mapping[name] == new.as_posix()
        mapping[name] = new.as_posix()
loader = '''"""Map reviewed Python import names to their hyphenated source files.

Only exact project modules in their original import directories are resolved.
"""
import sys
from importlib.machinery import PathFinder
from importlib.util import spec_from_file_location
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_FILES = {
''' + "".join("    " + repr(k) + ": " + repr(v) + ",\n" for k,v in sorted(mapping.items())) + '''}


class _FilenameFinder:
    """Resolve only known project modules in their original search directory."""

    def find_spec(self, fullname, path=None, target=None):
        relative = _FILES.get(fullname)
        if relative is None:
            return None
        source = _ROOT / relative
        for entry in sys.path if path is None else path:
            try:
                matches = Path(entry).resolve() == source.parent
            except (OSError, TypeError, ValueError):
                continue
            if matches:
                if not source.is_file():
                    raise ModuleNotFoundError(
                        f"Required PDF Magic source is missing: {relative}",
                        name=fullname,
                    )
                return spec_from_file_location(fullname, source)
        return None


sys.meta_path.insert(sys.meta_path.index(PathFinder), _FilenameFinder())
'''
edits = []
for p in files:
    if p in skip:
        continue
    try:
        original = p.read_bytes().decode("utf-8")
    except (OSError, UnicodeError):
        continue
    if "\0" in original:
        continue
    s = pattern.sub(lambda m: m.group().replace("_", "-"), original)
    if p.suffix == ".py":
        tree = ast.parse(s)
        lines = s.splitlines(keepends=True)
        # Precede every relevant import, preserving lexical scope and existing names.
        insertions = {}
        for node in ast.walk(tree):
            relevant = (
                isinstance(node, ast.ImportFrom) and module_names.search(node.module or "")
                or isinstance(node, ast.Import) and any(module_names.search(a.name) for a in node.names)
            )
            if relevant:
                line = lines[node.lineno - 1]
                indent = line[:len(line)-len(line.lstrip())]
                if node.col_offset != len(indent):
                    raise ValueError(f"Unexpected inline import {p}:{node.lineno}")
                insertions[node.lineno - 1] = indent + "__import__('module-loader')\n"
        if insertions and p.parts[0] == "scripts" and len(p.parts) > 1:
            i = min(insertions)
            indent = insertions[i][:-len("__import__('module-loader')\n")]
            depth = len(p.parts) - 1
            insertions[i] = (
                indent + "if __name__ == '__main__' and not __package__:\n" +
                indent + "    __import__('sys').path.append(str(__import__('pathlib').Path(__file__).resolve().parents[" + str(depth) + "]))\n" +
                insertions[i]
            )
        # Insert into complete embedded scripts, not textual source assertions.
        replacements = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            v = node.value
            if "\n" not in v and ";" not in v:
                continue
            try:
                ast.parse(v)
            except (SyntaxError, ValueError):
                continue
            new = import_line.sub(lambda m: m.group(1) + "__import__('module-loader'); ", v)
            new = re.sub(r"(?<=; )(?=import\s+(?:" + alternatives + r")\b)", "__import__('module-loader'); ", new)
            if v == new:
                continue
            old_literal = ast.get_source_segment(s,node)
            if not old_literal:
                continue
            # Keep the original physical line count so insertion offsets remain valid.
            a,b = node.lineno-1,node.end_lineno-1
            segment = "".join(lines[a:b+1])
            if old_literal in segment:
                replacement = repr(new) + "\n" * (b-a)
                updated = segment.replace(old_literal,replacement,1)
                replacements.append((a,b,updated))
        for a,b,updated in sorted(replacements, reverse=True):
            lines[a:b+1] = updated.splitlines(keepends=True)
        for i,value in sorted(insertions.items(), reverse=True):
            lines.insert(i,value)
        s = "".join(lines)
        if p.name == "ci_test_scope.py":
            for prefix in ("pdf", "enhanced", "protection", "maximum"):
                s = s.replace(f'name.startswith("{prefix}_")', f'name.startswith(("{prefix}_", "{prefix}-"))')
        ast.parse(s)
    elif p.suffix in (".yml", ".yaml"):
        s = import_line.sub(lambda m: m.group(1) + "__import__('module-loader'); ", s)
        s = re.sub(r'(")([ \t]*)(from (?:[\w.]+\.)?(?:' + alternatives + r') import)',r"\1\2__import__('module-loader'); \3",s)
    if p.name == "install-allow-and-open.sh":
        needle = '"$script_dir/scan-and-open.py"'
        assert needle in s
        s = s.replace(needle, needle + ' "$script_dir/module-loader.py"', 1)
    if s != original:
        p.write_bytes(s.encode("utf-8"))
        edits.append((p.as_posix(), moves.get(p,p).as_posix(), s))
for old,new in moves.items():
    old.rename(new)
loader_path = pathlib.Path("module-loader.py")
loader_path.write_text(loader)
edits.append((None, loader_path.as_posix(), loader))
batch = int(sys.argv[1])
selected = [item for i,item in enumerate(edits) if i % 12 == batch]
raw = json.dumps(selected, ensure_ascii=True, separators=(",", ":")).encode("ascii")
compressor = zlib.compressobj(level=9, wbits=-15, strategy=zlib.Z_FIXED)
packed = base64.b64encode(compressor.compress(raw)+compressor.flush()).decode("ascii")
print("CANDIDATE_COUNT", len(edits), "BATCH", batch, "ENTRIES", len(selected), "MOVES", len(moves))
for i in range(0,len(packed),3000):
    print("CANDIDATE_DATA", packed[i:i+3000])
print("CANDIDATE_END")
