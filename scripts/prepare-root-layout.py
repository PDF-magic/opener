#!/usr/bin/env python3
"""Prepare application module relocation in a disposable checkout; never pushes."""
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import difflib

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
GROUPS = {
    "src.browser": ("browser_preference_selector", "browser_release"),
    "src.configuration": ("configuration_loader", "configuration_validation"),
    "src.scan": ("detection_responses", "file_lifecycle", "scan_history_metadata",
                 "scan_history_record", "combined_scan_results", "document_security_report"),
    "src.native": ("native_message_format", "native_message_framing"),
    "src.protection": ("protection_exception_policy", "protection_failure_exception_boundary",
                       "protection_performance_evidence", "protection_stage_time_limits",
                       "effective_protection_policy", "missing_dependency_policy"),
    "src.scanner": ("scanner_failure_policy", "scanner_feature_check"),
    "scripts.installation": ("ask_scan_history_retention", "ask_uninstall_preferences",
                             "existing_finder_quick_action", "existing_signature_database",
                             "offer-restore-pdf-handler", "restore_finder_quick_action",
                             "signature_update_launchagent", "stop_owned_background_processes",
                             "uninstall_signature_launchagent", "uninstall_temporary_pdfs",
                             "verify-other-pdf-open"),
}
PACKAGES = {n:p for p, ns in GROUPS.items() for n in ns}
NAMES = tuple(PACKAGES)
PREFIXES = {n:p.replace(".", "/") + "/" for n,p in PACKAGES.items()}
PAT = "|".join(map(re.escape, sorted(NAMES, key=len, reverse=True)))
IMPORT_PAT = "|".join(map(re.escape, sorted((n for n in NAMES if "-" not in n), key=len, reverse=True)))
FILE_RE = re.compile(r"(?<![\w.-])(" + PAT + r")\.py(?![\w.-])")
FROM_RE = re.compile(r"(?m)^([ \t]*from[ \t]+)(" + IMPORT_PAT + r")(?=[ \t]+import\b)")
IMPORT_RE = re.compile(r"(?m)^([ \t]*)import[ \t]+(" + IMPORT_PAT + r")(?P<alias>[ \t]+as[ \t]+\w+)?(?=[ \t]*(?:#|$))")
DYNAMIC_RE = re.compile(r"(\b(?:import_module|patch)\s*\(\s*[\"'])(" + IMPORT_PAT + r")(?=[.\"'])")
HELPERS = {"scripts/prepare-root-layout.py", ".github/workflows/prepare-root-layout.yml"}
BOOTSTRAP = {"browser_preference_selector", "uninstall_signature_launchagent", "uninstall_temporary_pdfs"}
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

paths = [Path(os.fsdecode(p)) for p in subprocess.check_output(["git","ls-files","-z"]).split(b"\0") if p]
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
    new = rewrite(old,path)
    if path.parent == Path(".") and path.stem in NAMES and path.suffix == ".py":
        if path.stem in BOOTSTRAP:
            module = ast.parse(new)
            first = module.body[1] if (isinstance(module.body[0],ast.Expr) and isinstance(module.body[0].value,ast.Constant) and isinstance(module.body[0].value.value,str)) else module.body[0]
            lines = new.splitlines(keepends=True)
            lines.insert(first.lineno - 1,
                "# Direct execution from the source checkout.\n"
                "if __name__ == \"__main__\" and not __package__:\n"
                "    import sys as _layout_sys\n"
                "    from pathlib import Path as _LayoutPath\n"
                "    _layout_sys.path.insert(0, str(_LayoutPath(__file__).resolve().parents[2]))\n\n")
            new = "".join(lines)
        dest = Path(PREFIXES[path.stem]) / path.name
        assert not dest.exists(), dest
        stage(dest,str(path),new,path.stat().st_mode)
        path.unlink()
    elif new != old:
        if not str(path).startswith(("tests/","docs/","benchmarks/")):
            for line in difflib.unified_diff(old.splitlines(),new.splitlines(),n=0):
                if line.startswith(("+","-")) and not line.startswith(("+++","---")):
                    print("REFERENCE " + str(path) + " " + line,flush=True)
        stage(path,str(path),new,path.stat().st_mode)

for pkg in GROUPS:
    path = Path(pkg.replace(".","/")) / "__init__.py"
    assert not path.exists(),path
    stage(path,None,'"""' + pkg.split(".")[-1].title() + ' application helpers."""\n',0o644)

assert all(not Path(n+".py").exists() for n in NAMES)
for path, (_,content,_) in changes.items():
    if path.endswith(".py"):
        ast.parse(content,filename=path)
    print("CANDIDATE_CHANGE "+path,flush=True)
print("CANDIDATE_TOTAL "+str(len(changes)),flush=True)
for path,(previous,content,mode) in sorted(changes.items()):
    data=content.encode("utf-8")
    sha=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
    encoded=base64.b64encode(data).decode("ascii")
    chunks=[encoded[i:i+4096] for i in range(0,len(encoded),4096)] or [""]
    print("LAYOUT_META "+json.dumps([path,previous,"100755" if mode & 0o111 else "100644",sha,len(chunks)]),flush=True)
    for i,chunk in enumerate(chunks):
        print("LAYOUT_DATA "+json.dumps([path,i,chunk]),flush=True)
print("CANDIDATE_END",flush=True)
env=dict(os.environ,PYTHONPATH=str(ROOT))
failures=[]
tests=sorted(p for p in changes if p.startswith("tests/") and p.endswith(".py") and not p.endswith("__init__.py"))
for name in tests:
    print("ROOT_TEST "+name,flush=True)
    try:
        if subprocess.run([sys.executable,name,"-v"],env=env,timeout=120).returncode:
            failures.append(name)
    except subprocess.TimeoutExpired:
        failures.append(name)
print("ROOT_TEST_FAILURES "+json.dumps(failures),flush=True)
raise SystemExit(bool(failures))
