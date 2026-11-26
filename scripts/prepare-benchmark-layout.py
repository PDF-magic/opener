#!/usr/bin/env python3
"""Prepare a benchmark-only move in a disposable checkout. Never pushes."""
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
    "app_launch_benchmark", "cold_warm_scan_benchmark", "cpu_usage_benchmark",
    "enhanced_structure_benchmark", "large_pdf_benchmark",
    "many_embedded_objects_benchmark", "maximum_sanitization_benchmark",
    "medium_pdf_benchmark", "pdf_parser_memory_benchmark", "peak_memory_benchmark",
    "performance_regression_thresholds", "scanned_pdf_benchmark",
    "scanner_startup_benchmark", "signature_database_load_benchmark",
    "small_text_pdf_benchmark", "temporary_disk_benchmark",
    "ui_responsiveness_benchmark",
)
BOOTSTRAP = {
    "cold_warm_scan_benchmark", "cpu_usage_benchmark", "enhanced_structure_benchmark",
    "large_pdf_benchmark", "many_embedded_objects_benchmark", "maximum_sanitization_benchmark",
    "medium_pdf_benchmark", "peak_memory_benchmark", "scanned_pdf_benchmark",
    "small_text_pdf_benchmark", "temporary_disk_benchmark",
}
PAT = "|".join(map(re.escape, NAMES))
FILE_RE = re.compile(r"(?<![\w.-])(?:" + PAT + r")\.py(?![\w.-])")
FROM_RE = re.compile(r"(?m)^([ \t]*from[ \t]+)(" + PAT + r")(?=[ \t]+import\b)")
IMPORT_RE = re.compile(r"(?m)^([ \t]*)import[ \t]+(" + PAT + r")(?P<alias>[ \t]+as[ \t]+\w+)?(?=[ \t]*(?:#|$))")
HELPERS = {"scripts/prepare-benchmark-layout.py", ".github/workflows/prepare-benchmark-layout.yml"}
TESTS = (
    "tests/app/launch-benchmark.py", "tests/enhanced/structural-benchmark.py",
    "tests/maximum/sanitization-benchmark.py", "tests/maximum/temporary-disk-benchmark.py",
    "tests/pdf/large-pdf-benchmark.py", "tests/pdf/many-embedded-objects-benchmark.py",
    "tests/pdf/scanned-image-benchmark.py", "tests/pdf/small-text-benchmark.py",
    "tests/performance/cold-warm-scans.py", "tests/performance/cpu-usage.py",
    "tests/performance/medium-pdf.py", "tests/performance/regression-thresholds.py",
    "tests/performance/ui-responsiveness.py", "tests/scanner/peak-memory.py",
    "tests/scanner/signature-database-load-benchmark.py", "tests/scanner/startup-benchmark.py",
)

def git(*args):
    return subprocess.check_output(["git", *args])

def replace_import(m):
    return m.group(1) + ("import benchmarks." + m.group(2) + m.group("alias")
                         if m.group("alias") else "from benchmarks import " + m.group(2))

def rewrite(text, path):
    text = FILE_RE.sub(lambda m: m.group() if text[max(0, m.start()-11):m.start()] == "benchmarks/" else "benchmarks/" + m.group(), text)
    if path.suffix == ".py":
        text = FROM_RE.sub(r"\1benchmarks.\2", text)
        text = IMPORT_RE.sub(replace_import, text)
    return text

paths = [Path(os.fsdecode(p)) for p in git("ls-files", "-z").split(b"\0") if p]
changes = {}
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
        # Repository-only CLI tools need the checkout root for direct script launches,
        # including their subprocess worker modes. Do not change isolated DB benchmark.
        if path.stem in BOOTSTRAP:
            module = ast.parse(new)
            first = module.body[1] if (isinstance(module.body[0], ast.Expr)
                and isinstance(module.body[0].value, ast.Constant)
                and isinstance(module.body[0].value.value, str)) else module.body[0]
            lines = new.splitlines(keepends=True)
            lines.insert(first.lineno - 1, (
                "# Direct CLI and worker execution from a source checkout.\n"
                "if __name__ == \"__main__\" and not __package__:\n"
                "    import sys as _benchmark_sys\n"
                "    from pathlib import Path as _BenchmarkPath\n"
                "    _benchmark_sys.path.insert(0, str(_BenchmarkPath(__file__).resolve().parents[1]))\n\n"
            ))
            new = "".join(lines)
        if path.stem == "ui_responsiveness_benchmark":
            assert new.count("ROOT = Path(__file__).resolve().parent") == 1
            new = new.replace("ROOT = Path(__file__).resolve().parent", "ROOT = Path(__file__).resolve().parents[1]")
        dest = Path("benchmarks") / path.name
        assert not dest.exists(), dest
        dest.parent.mkdir(exist_ok=True)
        mode = path.stat().st_mode
        dest.write_bytes(new.encode("utf-8"))
        dest.chmod(mode)
        path.unlink()
        changes[str(dest)] = (str(path), new, mode)
    elif new != old:
        path.write_bytes(new.encode("utf-8"))
        changes[str(path)] = (str(path), new, path.stat().st_mode)
init = Path("benchmarks/__init__.py")
init.write_text('"""Development-only performance benchmarks; not installed scanner code."""\n')
changes[str(init)] = (None, init.read_text(), init.stat().st_mode)

assert all(not Path(name + ".py").exists() for name in NAMES)
for path, (_, content, _) in changes.items():
    if path.endswith(".py"):
        ast.parse(content, filename=path)
    print("CANDIDATE_CHANGE " + path, flush=True)
print("CANDIDATE_TOTAL " + str(len(changes)), flush=True)

# Emit a compact, structured candidate for the connector to review and apply.
# Files are public repository source only; never include environment or runtime data.
for path, (previous, content, mode) in sorted(changes.items()):
    record = json.dumps({"path": path, "previous": previous,
                         "mode": "100755" if mode & 0o111 else "100644",
                         "content": content}, ensure_ascii=True, separators=(",", ":"))
    chunks = [record[i:i + 3500] for i in range(0, len(record), 3500)]
    for i, chunk in enumerate(chunks):
        print("LAYOUT_CANDIDATE " + json.dumps([path, i, len(chunks), chunk], ensure_ascii=True), flush=True)
print("CANDIDATE_END", flush=True)
if "--test" in sys.argv:
    failures = []
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    for name in TESTS:
        result = subprocess.run([sys.executable, name, "-v"], env=env, timeout=120)
        if result.returncode:
            failures.append(name)
    print("BENCHMARK_TEST_FAILURES " + json.dumps(failures), flush=True)
    raise SystemExit(bool(failures))
