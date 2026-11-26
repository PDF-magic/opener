#!/usr/bin/env python3
"""Check the source layout and both fixed scanner import environments."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "src/scan/scan-and-open.py"
IMPORT_GATE = (
    "import importlib.util, sys; "
    "spec = importlib.util.spec_from_file_location('layout_scan_gate', sys.argv[1]); "
    "module = importlib.util.module_from_spec(spec); "
    "sys.modules[spec.name] = module; spec.loader.exec_module(module); "
    "assert module.ScanResult is not None"
)


class PythonSourceLayoutTests(unittest.TestCase):
    def test_no_root_source_or_runtime_files(self):
        tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
        names = [Path(name.decode()) for name in tracked.split(b"\0") if name]
        self.assertEqual([str(name) for name in names
                          if len(name.parts) == 1 and name.suffix in (".py", ".swift", ".sh", ".command", ".txt")], [])

    def test_scanner_imports_from_checkout_and_flat_installation(self):
        env = {**os.environ, "PYTHONPATH": "", "PYTHONDONTWRITEBYTECODE": "1"}
        subprocess.run([sys.executable, "-I", "-B", "-c", IMPORT_GATE, str(GATE)],
                       check=True, cwd="/", env=env)
        installer = (ROOT / "scripts/installation/install-allow-and-open.sh").read_text()
        copy_line = next(line for line in installer.splitlines()
                         if line.startswith('cp "$script_dir/src/scan/allow-and-open.sh"'))
        sources = re.findall(r'"\$script_dir/([^"]+\.py)"', copy_line)
        self.assertIn("src/module-loader.py", sources)
        self.assertIn("src/scan/scan-and-open.py", sources)
        with tempfile.TemporaryDirectory(prefix="opener-layout-") as directory:
            destination = Path(directory)
            for source in sources:
                shutil.copy2(ROOT / source, destination / Path(source).name)
            subprocess.run([sys.executable, "-I", "-B", "-c",
                            "import sys; sys.path.insert(0, sys.argv[2]); " + IMPORT_GATE,
                            str(destination / GATE.name), str(destination)],
                           check=True, cwd="/", env=env)


if __name__ == "__main__":
    unittest.main()
