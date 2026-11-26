#!/usr/bin/env python3
"""Paired benchmarks must use identical measurement and fixture sources."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
__import__('src.module-loader')
from compare_benchmark_layout import compare, legacy_medium, MEDIUM, FIXTURE


class BenchmarkLayoutTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.baseline = self.root / "baseline"
        self.candidate = self.root / "candidate"
        self.baseline.mkdir()
        (self.candidate / "benchmarks").mkdir(parents=True)
        for name in (MEDIUM, FIXTURE):
            (self.candidate / "benchmarks" / name).write_bytes(
                (ROOT / "benchmarks" / name).read_bytes())

    def prepare_baseline(self, packaged):
        folder = self.baseline / "benchmarks" if packaged else self.baseline
        folder.mkdir(exist_ok=True)
        for name in (MEDIUM, FIXTURE):
            source = (self.candidate / "benchmarks" / name).read_bytes()
            if not packaged and name == MEDIUM:
                source = legacy_medium(source)
            (folder / name).write_bytes(source)

    def test_current_layout_requires_identical_sources(self):
        self.prepare_baseline(True)
        self.assertEqual(compare(self.baseline, self.candidate), f"benchmarks/{MEDIUM}")
        path = self.candidate / "benchmarks" / FIXTURE
        path.write_bytes(path.read_bytes() + b"\n# different fixture\n")
        with self.assertRaisesRegex(ValueError, "Incomparable"):
            compare(self.baseline, self.candidate)

    def test_legacy_layout_only_permits_exact_layout_translation(self):
        self.prepare_baseline(False)
        self.assertEqual(compare(self.baseline, self.candidate), MEDIUM)
        path = self.candidate / "benchmarks" / MEDIUM
        path.write_bytes(path.read_bytes() + b"\n# different measurement\n")
        with self.assertRaisesRegex(ValueError, "Incomparable"):
            compare(self.baseline, self.candidate)

    def test_missing_baseline_is_rejected(self):
        with self.assertRaises(OSError):
            compare(self.baseline, self.candidate)


if __name__ == "__main__":
    unittest.main()
