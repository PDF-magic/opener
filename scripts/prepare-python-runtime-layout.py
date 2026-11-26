"""Relocate the remaining Python source files without changing installed paths."""
import base64
import os
from pathlib import Path
import posixpath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
moves = {
  "browser-registry.py": "src/browser/browser-registry.py",
  "file-launcher.py": "src/native/launch/file-launcher.py",
  "module-loader.py": "src/module-loader.py",
  "pdf-handler-status.py": "src/native/handler/pdf-handler-status.py",
  "record-scan-origin.py": "src/scan/record-scan-origin.py",
  "scan-and-open.py": "src/scan/scan-and-open.py",
  "scan-results.py": "src/scan/scan-results.py",
  "scanner-argument-validation.py": "src/scanner/scanner-argument-validation.py",
  "scanner-concurrency-validation.py": "src/scanner/scanner-concurrency-validation.py",
  "scanner-filesystem-sandbox.py": "src/scanner/scanner-filesystem-sandbox.py",
  "select-custom-pdf-application.py": "src/native/launch/select-custom-pdf-application.py",
  "signature-update-status.py": "src/scanner/signature-update-status.py",
}
runtime = ("browser-registry.py", "file-launcher.py", "scan-results.py",
           "scanner-argument-validation.py", "scanner-concurrency-validation.py",
           "scanner-filesystem-sandbox.py")
bootstrap = '''# The source checkout and installed flat helper directory have distinct layouts.
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_bootstrap_file = _BootstrapPath(__file__).resolve()
if _bootstrap_file.parent.name == CATEGORY and _bootstrap_file.parent.parent.name == PARENT:
    _bootstrap_sys.path.insert(0, str(_bootstrap_file.parents[DEPTH]))
    __import__("src.module-loader")
else:
    __import__("module-loader")
'''
def source_bootstrap(filename, category, parent, depth, text):
  code = bootstrap.replace("CATEGORY", repr(category)).replace("PARENT", repr(parent)).replace("DEPTH", str(depth))
  # Retain only the initial bootstrap; later imports use the registered finder.
  text, count = re.subn(r"(?m)^__import__\(['\"]src\.module-loader['\"]\)\n", lambda m: code, text, count=1)
  assert count == 1, filename
  return re.sub(r"(?m)^[ \t]*__import__\(['\"]src\.module-loader['\"]\)\n", "", text)

paths = subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
changed = {}
for filename in filter(None, paths):
  p = Path(filename)
  if p.name in ("prepare-python-runtime-layout.py", "validate-python-runtime-layout.yml"):
    continue
  if p.suffix not in (".py", ".md", ".swift", ".yml", ".yaml", ".sh", ".json", ".mjs", ".js", ".command"):
    continue
  try:
    original = p.read_bytes().decode("utf-8")
  except UnicodeDecodeError:
    continue
  updated = original
  # Existing import identifiers are unchanged; the fixed finder lives in src.
  updated = re.sub(r"(?<![\w.-])module-loader(?![\w.-])", "src.module-loader", updated)
  if filename == "module-loader.py":
    updated = updated.replace("_ROOT = Path(__file__).resolve().parent", "_DEPLOYED = __name__ == 'module-loader'\n_ROOT = Path(__file__).resolve().parent if _DEPLOYED else Path(__file__).resolve().parents[1]")
    for name, dest in moves.items():
      updated = updated.replace(repr(name), repr(dest))
    aliases = [n[:-3].replace("-", "_") for n in runtime]
    updated = updated.replace("class _FilenameFinder:", "_ROOT_ALIASES = _ROOT_ALIASES.union(" + repr(aliases) + ")\nif _DEPLOYED:\n    _FILES = {name: Path(_FILES[name]).name for name in " + repr(aliases) + "}\n    _ROOT_ALIASES = frozenset()\n\n\nclass _FilenameFinder:")
    # Undo the global textual replacement on the installed import-name check.
    assert "_DEPLOYED = __name__ == 'module-loader'" in updated
  elif filename == "scan-and-open.py":
    updated = source_bootstrap(filename, "scan", "src", 2, updated)
  elif filename == "file-launcher.py":
    updated = source_bootstrap(filename, "launch", "native", 3, updated)
  elif filename == "install-allow-and-open.sh":
    for name, destination in moves.items():
      updated = updated.replace("$script_dir/" + name, "$script_dir/" + destination)
    needle = '"$script_dir/src/scan/scan-results.py"'
    assert needle in updated
    updated = updated.replace(needle, needle + " " + " ".join('"$script_dir/' + moves[n] + '"' for n in runtime if n.startswith("scanner-")))
    # Repository helper scripts import src.module-loader by a fixed checkout
    # path, even when installation was launched from another working directory.
    updated = updated.replace('script_dir="$(cd "$(dirname "$0")" && pwd)"', 'script_dir="$(cd "$(dirname "$0")" && pwd)"\nexport PYTHONPATH="$script_dir"')
  elif filename == "scripts/preserve-existing-opener.py":
    updated = updated.replace('"allow-and-open.sh", "scan-and-open.py", "file-launcher.py",', '"allow-and-open.sh", "scan-and-open.py", "file-launcher.py",\n    "module-loader.py", "scanner-argument-validation.py",\n    "scanner-concurrency-validation.py", "scanner-filesystem-sandbox.py",')
  elif filename == "allow-and-open.sh":
    # The installed flat command remains unchanged; a source checkout uses its
    # fixed source paths, with no fallback when the checkout is incomplete.
    needle = '/usr/bin/python3 "$script_dir/record-scan-origin.py" "$@" >/dev/null 2>&1 || true'
    updated = updated.replace(needle, 'if [ -f "$script_dir/.gitattributes" ]; then\n    /usr/bin/python3 "$script_dir/src/scan/record-scan-origin.py" "$@" >/dev/null 2>&1 || true\n    exec /usr/bin/python3 "$script_dir/src/scan/scan-and-open.py" "$@"\nfi\n' + needle)
  else:
    for name, dest in moves.items():
      escaped = re.escape(name)
      # Explicit repository paths only. Keep installed locations, mock
      # runtime files, sandbox sibling basenames and test filenames intact.
      if filename != "tests/general/quarantine-removal-inventory.py":
        updated = re.sub(r'((?:ROOT|root|repository|repo_root|repo|original|Path\(__file__\)\.resolve\(\)\.parents\[2\])\s*/\s*["\x27])' + escaped, lambda m: m[1] + dest, updated)
      if p.suffix == ".md" or filename.startswith("extensions/webextension/tests/"):
        relative = posixpath.relpath(dest, p.parent.as_posix())
        updated = re.sub(r'(?<![\w/-])(?:\.\./)+' + escaped, relative, updated)
      if p.suffix in (".yml", ".yaml"):
        updated = re.sub(r'(?m)^(\s*-\s*["\x27]?)' + escaped + r'(["\x27]?\s*)$', lambda m: m[1] + dest + m[2], updated)
      if filename.startswith("tests/"):
        updated = updated.replace("$script_dir/" + name, "$script_dir/" + dest) if filename in (
          "tests/browser/registry.py", "tests/file/launcher.py", "tests/pdf/handler-status.py",
          "tests/signature/update-times.py",
        ) else updated
        # Only the installer source operand changes; installed target names
        # are preserved. Wrapper command assertions remain unchanged.
        if filename == "tests/browser/custom-selection.py":
          updated = re.sub(r'(load\("[^"]+",\s*")' + escaped + r'(")', lambda m: m[1] + dest + m[2], updated)
    if filename in ("src/sanitization/maximum-safe-copy-handoff.py", "src/sanitization/maximum-save-sanitized-copy.py"):
      updated = updated.replace('parents[2] / "scan-and-open.py"', 'parents[1] / "scan/scan-and-open.py"')
    if filename == "tests/maximum/safe-copy-handoff.py":
      updated = updated.replace('with_name("scan-and-open.py")', 'parents[1] / "scan/scan-and-open.py"')
      updated = updated.replace('Path(route.__file__).parent / "scan-and-open.py"', 'Path(route.__file__).resolve().parents[1] / "scan/scan-and-open.py"')
    if filename == "tests/browser/registry.py":
      updated = updated.replace('../browser-registry.py', '../src/browser/browser-registry.py')
    if filename == "extensions/webextension/tests/browser-automatic-interception-research.test.mjs" or filename == "extensions/webextension/tests/browser-unsupported-routes.test.mjs":
      updated = updated.replace('read("browser-registry.py")', 'read("src/browser/browser-registry.py")')
    if filename == "tools/audit-quarantine-removal.py":
      updated = updated.replace('LEGACY = "scan-and-open.py"', 'LEGACY = "src/scan/scan-and-open.py"')
    if filename == "tests/general/quarantine-removal-inventory.py":
      updated = updated.replace('"scan-and-open.py"', '"src/scan/scan-and-open.py"')
      updated = updated.replace('(root / "src/scan/scan-and-open.py").write_text(', '(root / "src/scan").mkdir(parents=True)\n            (root / "src/scan/scan-and-open.py").write_text(')
    if filename == "scripts/ci-test-scope.py":
      updated = updated.replace('or name.startswith("requirements")', 'or name == "module-loader.py"\n            or name.startswith("requirements")')
  if updated != original:
    changed[filename] = updated
    p.write_bytes(updated.encode("utf-8"))

for name, dest in sorted(moves.items()):
  p = Path(dest)
  assert not p.exists()
  p.parent.mkdir(parents=True, exist_ok=True)
  Path(name).rename(p)
  print("MOVE " + name + " " + dest)
assert not list(ROOT.glob("*.py"))
# Verify the exact installed layout using only the files the installer copies.
import shutil
import tempfile
with tempfile.TemporaryDirectory(prefix="opener-flat-runtime-") as directory:
  install = Path(directory)
  for name in (*runtime, "module-loader.py", "scan-and-open.py"):
    shutil.copy2(ROOT / moves[name], install / name)
  subprocess.run([os.environ.get("PYTHON", "python3"), "-c",
    "import importlib.util, sys; sys.path.insert(0, sys.argv[1]); spec = importlib.util.spec_from_file_location('scan_gate', sys.argv[1] + '/scan-and-open.py'); m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m; spec.loader.exec_module(m); assert m.ScanResult is not None",
    str(install)], check=True, cwd="/", env={**os.environ, "PYTHONPATH": ""})
for filename, updated in sorted(changed.items()):
  encoded = base64.b64encode(updated.encode()).decode()
  print("CANDIDATE_BEGIN " + filename)
  for start in range(0, len(encoded), 6000):
    print("CANDIDATE_DATA " + encoded[start:start+6000])
  print("CANDIDATE_END")
print("CANDIDATE_COMPLETE")
