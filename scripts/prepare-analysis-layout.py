#!/usr/bin/env python3
"""Prepare passive analysis module moves in a disposable checkout; never pushes."""
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
NAMES = (
    "enhanced_additional_inspections", "enhanced_analysis_findings",
    "enhanced_analysis_timing", "enhanced_blocking_policy",
    "enhanced_embedded_files", "enhanced_finding_explanations",
    "enhanced_inconclusive_results", "pdf_action_chains", "pdf_annotations",
    "pdf_automatic_actions", "pdf_automatic_external_requests",
    "pdf_behavior_classification", "pdf_declared_metadata",
    "pdf_decompression_requirements", "pdf_document_permissions",
    "pdf_embedded_executable_content", "pdf_embedded_file_types",
    "pdf_embedded_filenames", "pdf_embedded_object_sizes", "pdf_encryption_policy",
    "pdf_external_launch_actions", "pdf_form_actions", "pdf_format_identification",
    "pdf_incremental_revisions", "pdf_javascript_actions", "pdf_malformed_structures",
    "pdf_object_relationships", "pdf_repeated_structures", "pdf_revision_active_content",
    "pdf_rich_media", "pdf_stream_lengths", "pdf_structure_ambiguity",
    "pdf_suspicious_urls", "pdf_unsupported_feature_inspection",
    "pdf_unusual_object_counts", "pdf_xfa_forms", "unsupported_pdf_features",
)
PACKAGES = {n: ("src.enhanced" if n.startswith("enhanced_") else "src.pdf") for n in NAMES}
PREFIXES = {n: p.replace(".", "/") + "/" for n, p in PACKAGES.items()}
PAT = "|".join(map(re.escape, sorted(NAMES, key=len, reverse=True)))
FILE_RE = re.compile(r"(?<![\w.-])(" + PAT + r")\.py(?![\w.-])")
FROM_RE = re.compile(r"(?m)^([ \t]*from[ \t]+)(" + PAT + r")(?=[ \t]+import\b)")
IMPORT_RE = re.compile(r"(?m)^([ \t]*)import[ \t]+(" + PAT + r")(?P<alias>[ \t]+as[ \t]+\w+)?(?=[ \t]*(?:#|$))")
DYNAMIC_RE = re.compile(r"(\b(?:import_module|patch)\s*\(\s*[\"'])(" + PAT + r")(?=[.\"'])")
HELPERS = {"scripts/prepare-analysis-layout.py", ".github/workflows/prepare-analysis-layout.yml"}
changes = {}


def rewrite(text, path):
    def file_ref(match):
        prefix = PREFIXES[match.group(1)]
        return match.group() if text[max(0, match.start()-len(prefix)):match.start()] == prefix else prefix + match.group()
    text = FILE_RE.sub(file_ref, text)
    if path.suffix in (".py", ".md"):
        text = FROM_RE.sub(lambda m: m.group(1) + PACKAGES[m.group(2)] + "." + m.group(2), text)
        text = IMPORT_RE.sub(lambda m: m.group(1) + (
            "import " + PACKAGES[m.group(2)] + "." + m.group(2) + m.group("alias")
            if m.group("alias") else "from " + PACKAGES[m.group(2)] + " import " + m.group(2)), text)
        text = DYNAMIC_RE.sub(lambda m: m.group(1) + PACKAGES[m.group(2)] + "." + m.group(2), text)
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
        dest = Path(PREFIXES[path.stem]) / path.name
        assert not dest.exists(), dest
        stage(dest, str(path), new, path.stat().st_mode)
        path.unlink()
    elif new != old:
        if path.parent == Path(".") and path.suffix == ".py":
            import difflib
            for line in difflib.unified_diff(old.splitlines(), new.splitlines(), n=0):
                if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                    print("ROOT_REFERENCE " + str(path) + " " + line, flush=True)
        stage(path, str(path), new, path.stat().st_mode)

for name, description in (
    ("src/__init__.py", "PDF Magic Opener application source packages."),
    ("src/pdf/__init__.py", "Passive PDF inspection and format analysis."),
    ("src/enhanced/__init__.py", "Enhanced analysis evidence and policy helpers."),
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
    data = content.encode("utf-8")
    sha = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    encoded = base64.b64encode(data).decode("ascii")
    chunks = [encoded[i:i + 4096] for i in range(0, len(encoded), 4096)] or [""]
    print("LAYOUT_META " + json.dumps([path, previous, "100755" if mode & 0o111 else "100644", sha, len(chunks)]), flush=True)
    for i, chunk in enumerate(chunks):
        print("LAYOUT_DATA " + json.dumps([path, i, chunk]), flush=True)
print("CANDIDATE_END", flush=True)
failures = []
env = dict(os.environ, PYTHONPATH=str(ROOT))
tests = sorted(path for path in changes if path.startswith("tests/") and path.endswith(".py") and not path.endswith("__init__.py"))
for name in tests:
    print("ANALYSIS_TEST " + name, flush=True)
    try:
        result = subprocess.run([sys.executable, name, "-v"], env=env, timeout=120)
        if result.returncode:
            failures.append(name)
    except subprocess.TimeoutExpired:
        failures.append(name)
print("ANALYSIS_TEST_FAILURES " + json.dumps(failures), flush=True)
raise SystemExit(bool(failures))
