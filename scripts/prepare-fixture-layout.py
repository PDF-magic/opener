#!/usr/bin/env python3
"""Prepare a test-fixture source move in a disposable checkout; never pushes."""
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
NAMES = (
    "deep_object_reference_corpus", "digital_signature_corpus", "embedded_file_corpus",
    "encrypted_pdf_collection", "external_launch_action_corpus", "interactive_form_corpus",
    "javascript_action_corpus", "large_valid_pdf_corpus", "malformed_object_stream_corpus",
    "malformed_xref_pdf_collection", "memory_stress_pdf_corpus", "oversized_stream_corpus",
    "reference_pdf_collection", "unicode_metadata_corpus",
)
PREFIX = "tests/fixtures/pdf/"
PACKAGE = "tests.fixtures.pdf"
PAT = "|".join(map(re.escape, NAMES))
FILE_RE = re.compile(r"(?<![\w.-])(?:" + PAT + r")\.py(?![\w.-])")
FROM_RE = re.compile(r"(?m)^([ \t]*from[ \t]+)(" + PAT + r")(?=[ \t]+import\b)")
IMPORT_RE = re.compile(r"(?m)^([ \t]*)import[ \t]+(" + PAT + r")(?P<alias>[ \t]+as[ \t]+\w+)?(?=[ \t]*(?:#|$))")
HELPERS = {"scripts/prepare-fixture-layout.py", ".github/workflows/prepare-fixture-layout.yml"}
changes = {}


def rewrite(text, path):
    text = FILE_RE.sub(lambda m: m.group() if text[max(0, m.start()-len(PREFIX)):m.start()] == PREFIX else PREFIX + m.group(), text)
    if path.suffix == ".py":
        text = FROM_RE.sub(lambda m: m.group(1) + PACKAGE + "." + m.group(2), text)
        text = IMPORT_RE.sub(lambda m: m.group(1) + (
            "import " + PACKAGE + "." + m.group(2) + m.group("alias")
            if m.group("alias") else "from " + PACKAGE + " import " + m.group(2)), text)
    return text


def stage(path, previous, new, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(new.encode("utf-8"))
    path.chmod(mode)
    changes[str(path)] = (previous, new, mode)


paths = [Path(os.fsdecode(p)) for p in subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0") if p]
for path in paths:
    if str(path) in HELPERS or not path.is_file() or path.is_symlink():
        continue
    raw = path.read_bytes()
    if b"\0" in raw:
        continue
    try:
        old = raw.decode("utf-8")
    except UnicodeDecodeError:
        continue
    new = rewrite(old, path)
    if path.parent == Path(".") and path.stem in NAMES and path.suffix == ".py":
        dest = Path(PREFIX) / path.name
        assert not dest.exists(), dest
        stage(dest, str(path), new, path.stat().st_mode)
        path.unlink()
    elif new != old:
        assert str(path).startswith(("tests/", "benchmarks/", "docs/", ".github/")) or str(path) == "README.md", f"unexpected runtime dependency: {path}"
        stage(path, str(path), new, path.stat().st_mode)

for name, description in (
    ("tests/__init__.py", "Repository regression tests and development fixtures."),
    ("tests/fixtures/__init__.py", "Development-only test fixtures."),
    ("tests/fixtures/pdf/__init__.py", "Synthetic PDF fixture generators."),
):
    path = Path(name)
    assert not path.exists()
    stage(path, None, f'"""{description}"""\n', 0o644)

assert all(not Path(name + ".py").exists() for name in NAMES)
for path, (_, content, _) in changes.items():
    if path.endswith(".py"):
        ast.parse(content, filename=path)
    print("CANDIDATE_CHANGE " + path, flush=True)
print("CANDIDATE_TOTAL " + str(len(changes)), flush=True)
for path, (previous, content, mode) in sorted(changes.items()):
    record = json.dumps({"path": path, "previous": previous, "mode": "100755" if mode & 0o111 else "100644", "content": content}, ensure_ascii=True, separators=(",", ":"))
    chunks = [record[i:i + 3500] for i in range(0, len(record), 3500)]
    for i, chunk in enumerate(chunks):
        print("LAYOUT_CANDIDATE " + json.dumps([path, i, len(chunks), chunk], ensure_ascii=True), flush=True)
print("CANDIDATE_END", flush=True)
failures = []
env = dict(os.environ, PYTHONPATH=str(ROOT))
tests = sorted(path for path in changes if path.startswith("tests/") and path.endswith(".py")
               and not path.startswith(PREFIX) and not path.endswith("__init__.py"))
for name in tests:
    print("FIXTURE_TEST " + name, flush=True)
    try:
        result = subprocess.run([sys.executable, name, "-v"], env=env, timeout=120)
        if result.returncode:
            failures.append(name)
    except subprocess.TimeoutExpired:
        failures.append(name)
print("FIXTURE_TEST_FAILURES " + json.dumps(failures), flush=True)
raise SystemExit(bool(failures))
