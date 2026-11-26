"""Prepare and verify source-only Python relocations in a disposable checkout."""
import base64
from pathlib import Path
import re
import subprocess
import os

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
moves = {}
for p in ROOT.glob("*.py"):
  name = p.name
  if name.startswith("maximum-") or name.startswith("protection-"):
    # Keep the exact same-directory allowlist used by the renderer.
    category = "protection"
    if name in {
      "maximum-active-content-removal.py", "maximum-generated-rescan.py",
      "maximum-overwrite-warning.py", "maximum-safe-copy-handoff.py",
      "maximum-sanitized-copy.py", "maximum-sanitized-structure.py",
      "maximum-save-sanitized-copy.py", "maximum-save-sanitized-pdf-action.py",
      "maximum-temporary-output.py", "maximum-view-sanitized-pdf.py",
    }:
      category = "sanitization"
    moves[name] = f"src/{category}/{name}"
  elif name.startswith(("timed-pdf-", "parser-filesystem-", "pdf-stream-", "pdf-structure-")):
    moves[name] = f"src/pdf/{name}"

paths = subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
changed = {}
for filename in filter(None, paths):
  p = Path(filename)
  if p.name in ("prepare-python-root-layout.py", "audit-python-root-layout.yml"):
    continue
  if p.suffix not in (".py", ".md", ".swift", ".yml", ".sh", ".json"):
    continue
  try:
    original = p.read_bytes().decode("utf-8")
  except UnicodeDecodeError:
    continue
  updated = original
  if filename == "module-loader.py":
    aliases = sorted(n[:-3].replace("-", "_") for n in moves)
    for name, destination in moves.items():
      updated = updated.replace(repr(name), repr(destination))
    updated = updated.replace("class _FilenameFinder:", "_ROOT_ALIASES = frozenset(" + repr(aliases + ["maximum-network-isolation"]) + ")\n_FILES['maximum-network-isolation'] = _FILES['maximum_network_isolation']\n\n\nclass _FilenameFinder:")
    updated = updated.replace("matches = Path(entry).resolve() == source.parent", "directory = Path(entry).resolve()\n                matches = directory == source.parent or (fullname in _ROOT_ALIASES and directory == _ROOT)")
  elif filename in moves:
    updated = updated.replace("os.path.dirname(os.path.realpath(__file__))", "os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))")
    if filename in ("maximum-safe-copy-handoff.py", "maximum-save-sanitized-copy.py"):
      updated = updated.replace('Path(__file__).resolve().with_name("scan-and-open.py")', 'Path(__file__).resolve().parents[2] / "scan-and-open.py"')
    if filename == "maximum-sanitized-copy.py":
      updated = updated.replace('Path(__file__).resolve().with_name("maximum-sanitized-copy")', 'Path(__file__).resolve().parents[2] / "maximum-sanitized-copy"')
    if filename == "maximum-sanitizer-process.py":
      updated = updated.replace('_network_isolation = import_module(', "__import__('module-loader')\n_network_isolation = import_module(")
  else:
    for name, destination in moves.items():
      # Update repository paths, not sibling worker basenames, test names,
      # runtime allowlist literals, or installed program names.
      escaped = re.escape(name)
      updated = re.sub(r'((?:ROOT|root|repository|repo_root|Path\(__file__\)\.resolve\(\)\.parents\[2\])\s*/\s*["\x27])' + escaped, lambda m: m[1] + destination, updated)
      if p.suffix == ".md":
        import posixpath
        relative = posixpath.relpath(destination, p.parent.as_posix())
        updated = re.sub(r'(?<![\w/-])(?:\.\./)+' + escaped, relative, updated)
      if p.suffix == ".yml":
        updated = re.sub(r'(?m)^(\s*-\s*)' + escaped + r'$', lambda m: m[1] + destination, updated)
    if filename == "tests/maximum/isolated-renderer.py":
      updated = updated.replace('source_root = Path(__file__).resolve().parents[2]', 'source_root = Path(renderer.__file__).resolve().parent')
    if filename == "tests/scan/progress-component.py":
      updated = updated.replace('COMPONENT.with_name("maximum-sanitized-copy.py")', '(COMPONENT.parents[2] / "src/sanitization/maximum-sanitized-copy.py")')
    if filename == "scripts/ci-test-scope.py":
      updated = updated.replace("path in SHARED_SECURITY_FILES", "name in SHARED_SECURITY_FILES")
    if filename.startswith("tests/") and 'import_module("maximum-network-isolation")' in updated:
      # The project already explicitly imports its allowlisted finder.
      updated = re.sub(r'(?m)^(\s*)(isolation = import_module\("maximum-network-isolation"\))', lambda m: m[1] + "__import__('module-loader')\n" + m[1] + m[2], updated)
  if updated != original:
    changed[filename] = updated
    p.write_bytes(updated.encode("utf-8"))

for name, destination in sorted(moves.items()):
  dest = Path(destination)
  assert not dest.exists()
  dest.parent.mkdir(parents=True, exist_ok=True)
  Path(name).rename(dest)
  print("MOVE " + name + " " + destination)
for filename, updated in sorted(changed.items()):
  encoded = base64.b64encode(updated.encode()).decode()
  print("CANDIDATE_BEGIN " + filename)
  for start in range(0, len(encoded), 6000):
    print("CANDIDATE_DATA " + encoded[start:start+6000])
  print("CANDIDATE_END")
print("CANDIDATE_COMPLETE")
