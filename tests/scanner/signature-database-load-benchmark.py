#!/usr/bin/env python3
"""opener-1072: measure signature loading without modifying scanner admission."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "signature_database_load_benchmark", ROOT / "signature_database_load_benchmark.py"
)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class SignatureLoadBenchmarkTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.library = self.root / "libclamav.dylib"
        self.library.write_bytes(b"synthetic test placeholder")
        self.database = self.root / "db"
        self.database.mkdir()
        (self.database / "main.cvd").write_bytes(b"test")
        (self.database / "daily.cld").write_bytes(b"test")
        trusted = patch.object(benchmark, "TRUSTED_LIBRARIES", (str(self.library),))
        trusted.start()
        self.addCleanup(trusted.stop)

    def sample(self, load=10.0, compile=3.0, count=200):
        return {"loadMs": load, "compileMs": compile,
                "readyMs": load + compile, "signatureCount": count,
                "engineVersion": "1.4.0"}

    def test_reject_untrusted_or_incomplete_databases_and_bad_counts(self):
        with self.assertRaises(benchmark.BenchmarkError):
            benchmark.measure("/usr/bin/env", self.database)
        with self.assertRaises(benchmark.BenchmarkError):
            benchmark.measure(str(self.library), self.root / "absent")
        for value in (2, 8, True, 3.5):
            with self.subTest(value=value), self.assertRaises(benchmark.BenchmarkError):
                benchmark.measure(str(self.library), self.database, value)
        (self.database / "main.cvd").unlink()
        with self.assertRaises(benchmark.BenchmarkError):
            benchmark.measure(str(self.library), self.database)
        (self.database / "main.cvd").symlink_to(self.library)
        with self.assertRaises(benchmark.BenchmarkError):
            benchmark.measure(str(self.library), self.database)
        (self.database / "main.cvd").unlink()
        (self.database / "main.cvd").write_bytes(b"test")
        (self.database / "main.cld").write_bytes(b"duplicate")
        with self.assertRaises(benchmark.BenchmarkError):
            benchmark.measure(str(self.library), self.database)

    def test_warmup_independent_samples_and_aggregate_only(self):
        samples = [self.sample(999, 12), self.sample(10, 3),
                   self.sample(20, 4), self.sample(30, 5)]
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            self.assertEqual(kwargs, {"capture_output": True, "text": True,
                                      "timeout": 180, "check": False})
            self.assertEqual(args[1], "-I")
            self.assertIn("--child", args)
            self.assertEqual(args[args.index("--library") + 1], str(self.library))
            return subprocess.CompletedProcess(args, 0, json.dumps(samples[len(calls) - 1]), "")
        report = benchmark.measure(str(self.library), self.database, 3, runner=runner)
        self.assertEqual(len(calls), 4)
        self.assertEqual(report["medianLoadMs"], 20.0)
        self.assertEqual(report["p90LoadMs"], 30.0)
        self.assertEqual(report["medianCompileMs"], 4.0)
        self.assertEqual(report["medianReadyMs"], 24.0)
        self.assertEqual(report["sampleCount"], 3)
        self.assertFalse(report["scannerVerdict"])
        self.assertEqual(report["scope"], "libclamavSignatureDatabaseLoad")
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("authorizesOpen", report)

    def test_abort_on_failure_timeout_nonfinite_or_signature_change(self):
        bad = [
            subprocess.CompletedProcess([], 2, "", "private/path"),
            subprocess.CompletedProcess([], 0, json.dumps(self.sample()), "warning"),
            subprocess.CompletedProcess([], 0, "{", ""),
            subprocess.CompletedProcess([], 0, json.dumps({**self.sample(), "loadMs": float("nan")}), ""),
            subprocess.CompletedProcess([], 0, json.dumps({**self.sample(), "signatureCount": 0}), ""),
        ]
        for result in bad:
            with self.subTest(result=result), self.assertRaises(benchmark.BenchmarkError):
                benchmark.measure(str(self.library), self.database, runner=lambda *a, **kw: result)
        with self.assertRaises(benchmark.BenchmarkError):
            benchmark.measure(str(self.library), self.database,
                              runner=lambda *a, **kw: (_ for _ in ()).throw(
                                  subprocess.TimeoutExpired("test", 180)))
        idx = iter([self.sample()] + [self.sample(count=n) for n in (200, 201, 200)])
        with self.assertRaises(benchmark.BenchmarkError):
            benchmark.measure(str(self.library), self.database, 3,
                              runner=lambda *a, **kw: subprocess.CompletedProcess(
                                  a, 0, json.dumps(next(idx)), ""))

    def test_direct_native_load_and_compile_are_separate(self):
        calls = []
        class Function:
            def __init__(self, name, func):
                self.name, self.func = name, func
            def __call__(self, *args):
                calls.append(self.name)
                return self.func(*args)
        class API:
            pass
        api = API()
        api.cl_init = Function("init", lambda flags: 0)
        api.cl_engine_new = Function("new", lambda: 42)
        def load(path, engine, count, flags):
            self.assertEqual(path, bytes(self.database))
            self.assertEqual(flags, 0)
            count._obj.value = 200
            return 0
        api.cl_load = Function("load", load)
        api.cl_engine_compile = Function("compile", lambda engine: 0)
        api.cl_engine_free = Function("free", lambda engine: 0)
        api.cl_retver = Function("version", lambda: b"1.4.0")
        ticks = iter((1.0, 1.01, 1.014))
        sample = benchmark.native_sample(str(self.library), self.database,
                                         loader=lambda path: api,
                                         clock=lambda: next(ticks))
        self.assertAlmostEqual(sample["loadMs"], 10)
        self.assertAlmostEqual(sample["compileMs"], 4)
        self.assertEqual(calls, ["init", "new", "load", "compile", "version", "free"])

    def test_benchmark_never_participates_in_live_scan_or_settings(self):
        live = (ROOT / "scan-and-open.py").read_text()
        self.assertNotIn("signature_database_load_benchmark", live)
        self.assertNotIn("cl_engine_new", live)
        self.assertNotIn("cl_engine_compile", live)
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("python3 tests/scanner/signature-database-load-benchmark.py -v", ci)
        readme = (ROOT / "README.md").read_text()
        self.assertIn("signature_database_load_benchmark.py", readme)


if __name__ == "__main__":
    unittest.main()
