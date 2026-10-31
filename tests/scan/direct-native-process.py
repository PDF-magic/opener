#!/usr/bin/env python3
"""opener-0847: native scanner executes Python directly, not a command shell.

Runs a real Swift Process with synthetic Python fixtures on macOS; the
cross-platform source contract also protects the fixed launch arguments.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SWIFT = ROOT / "brave-pdf-opener.swift"
BEGIN = "// BEGIN NATIVE DIRECT PROCESS GATE"
END = "// END NATIVE DIRECT PROCESS GATE"


class DirectNativeProcessTests(unittest.TestCase):
    def test_native_process_uses_literal_python_argv_and_keeps_origin(self):
        source = SWIFT.read_text(encoding="utf-8")
        self.assertEqual(source.count(BEGIN), 1)
        self.assertEqual(source.count(END), 1)
        block = source.split(BEGIN, 1)[1].split(END, 1)[0]
        self.assertEqual(block.count('URL(fileURLWithPath: "/usr/bin/python3")'), 2)
        self.assertEqual(block.count("arguments = [script.path, path]"), 2)
        self.assertNotIn("/bin/bash", block)
        self.assertNotIn("/bin/sh", block)
        self.assertNotRegex(block, r"(?i)shell\s*=|\-c\b")
        self.assertIn("makeNativeScanProcess(", source.split("private func startScan(", 1)[1])
        self.assertIn("recordNativeScanOrigin(script: originScript", source)
        self.assertIn('environment["PDF_MAGIC_NATIVE_CANCEL"] = "1"', source)
        self.assertIn('environment["PDF_MAGIC_PARENT_LIFETIME"] = "1"', source)
        self.assertIn('environment["PDF_MAGIC_REQUEST_ORIGIN"] = origin', source)
        self.assertIn('appendingPathComponent("record-scan-origin.py")', source)
        self.assertNotIn('process.executableURL = URL(fileURLWithPath: "/bin/bash")', source)
        self.assertIn("nativeScanProcessTimeout: TimeInterval = 35 * 60", source)
        self.assertIn("nativeOriginProcessTimeout: TimeInterval = 2", source)
        self.assertIn("timeout: nativeScanProcessTimeout", source)
        self.assertIn("timeout: nativeOriginProcessTimeout", source)
        self.assertIn("let finishedInTime = waitForNativeProcess(", source)
        self.assertIn("let output = diagnostic.finish(errors)", source)
        self.assertIn("if !finishedInTime {", source)
        # Finder continues to use its required macOS Run Shell Script action.
        self.assertIn('exec /usr/bin/python3 "$script_dir/scan-and-open.py" "$@"',
                      (ROOT / "allow-and-open.sh").read_text(encoding="utf-8"))

    @unittest.skipUnless(sys.platform == "darwin", "Swift Foundation Process test runs on macOS")
    def test_real_process_does_not_interpret_shell_special_document_path(self):
        source = SWIFT.read_text(encoding="utf-8")
        helpers = source.split(BEGIN, 1)[1].split(END, 1)[0]
        with tempfile.TemporaryDirectory(prefix="opener-0847-") as name:
            folder = Path(name)
            gate = folder / "synthetic-scan-and-open.py"
            origin = folder / "synthetic-record-scan-origin.py"
            origin_output = folder / "origin.json"
            injected_marker = folder / "unexpected-shell-execution"
            selected = str(folder / "$(touch unexpected-shell-execution); 'private' document.pdf")
            gate.write_text(
                'import json, os, sys\n'
                'print(json.dumps({"argv": sys.argv[1:], "origin": os.environ.get("PDF_MAGIC_REQUEST_ORIGIN"), '
                '"native": os.environ.get("PDF_MAGIC_NATIVE_CANCEL"), '
                '"lifetime": os.environ.get("PDF_MAGIC_PARENT_LIFETIME")}))\n',
                encoding="utf-8",
            )
            origin.write_text(
                'import json, os, pathlib, sys\n'
                'pathlib.Path(os.environ["ORIGIN_TEST_OUTPUT"]).write_text('
                'json.dumps({"args": sys.argv[1:], '
                '"origin": os.environ.get("PDF_MAGIC_REQUEST_ORIGIN")}))\n',
                encoding="utf-8",
            )
            harness = folder / "main.swift"
            harness.write_text(
                'import Foundation\n' + helpers + '''
let scanner = URL(fileURLWithPath: CommandLine.arguments[1])
let origin = URL(fileURLWithPath: CommandLine.arguments[2])
let output = CommandLine.arguments[3]
let document = CommandLine.arguments[4]
var env = ProcessInfo.processInfo.environment
env["PDF_MAGIC_NATIVE_CANCEL"] = "1"
env["PDF_MAGIC_PARENT_LIFETIME"] = "1"
env["PDF_MAGIC_REQUEST_ORIGIN"] = "desktop-application"
env["ORIGIN_TEST_OUTPUT"] = output
let lifetime = Pipe()
let errors = Pipe()
let process = makeNativeScanProcess(
    script: scanner, path: document, lifetime: lifetime,
    errors: errors, environment: env)
guard process.executableURL?.path == "/usr/bin/python3" else {
    fatalError("A shell was selected instead of Python")
}
guard process.arguments == [scanner.path, document] else {
    fatalError("Document path was not preserved as one literal argument")
}
let standardOutput = Pipe()
process.standardOutput = standardOutput
try process.run()
standardOutput.fileHandleForWriting.closeFile()
let data = standardOutput.fileHandleForReading.readDataToEndOfFile()
process.waitUntilExit()
guard process.terminationStatus == 0 else { fatalError("Synthetic scanner failed") }
FileHandle.standardOutput.write(data)
recordNativeScanOrigin(script: origin, path: document, environment: env)
''',
                encoding="utf-8",
            )
            executable = folder / "native-direct-test"
            subprocess.run(
                ["xcrun", "swiftc", "-warnings-as-errors", str(harness), "-o", str(executable)],
                check=True, capture_output=True, text=True, timeout=90,
            )
            completed = subprocess.run(
                [str(executable), str(gate), str(origin), str(origin_output), selected],
                capture_output=True, text=True, check=True, timeout=30,
            )
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["argv"], [selected])
            self.assertEqual(payload["origin"], "desktop-application")
            self.assertEqual(payload["native"], "1")
            self.assertEqual(payload["lifetime"], "1")
            self.assertEqual(json.loads(origin_output.read_text()),
                             {"args": [selected], "origin": "desktop-application"})
            self.assertFalse(injected_marker.exists())
            self.assertFalse((folder / "unexpected-shell-execution").exists())

    @unittest.skipUnless(sys.platform == "darwin", "Bounded Swift Process test requires macOS")
    def test_native_execution_deadline_terminates_stalled_subprocess(self):
        source = SWIFT.read_text(encoding="utf-8")
        helpers = source.split(BEGIN, 1)[1].split(END, 1)[0]
        with tempfile.TemporaryDirectory(prefix="opener-0852-") as directory:
            root = Path(directory)
            sleeping = root / "unresponsive.py"
            sleeping.write_text("import time\\ntime.sleep(30)\\n", encoding="utf-8")
            harness = root / "deadline.swift"
            harness.write_text(
                "import Foundation\\nimport Darwin\\n" + helpers + """
let process = Process()
process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
process.arguments = [CommandLine.arguments[1]]
process.standardOutput = FileHandle.nullDevice
process.standardError = FileHandle.nullDevice
let finished = DispatchSemaphore(value: 0)
process.terminationHandler = { _ in finished.signal() }
try process.run()
let started = Date()
let succeeded = waitForNativeProcess(process, completion: finished, timeout: 0.15)
precondition(!succeeded, "Overdue subprocess must not complete successfully")
precondition(Date().timeIntervalSince(started) < 5, "Overdue subprocess must stop promptly")
precondition(!process.isRunning, "Timed-out subprocess must be terminated")
print("PASS: timed-out native Process is terminated and cannot authorize opening")
""",
                encoding="utf-8",
            )
            executable = root / "deadline"
            subprocess.run(["xcrun", "swiftc", "-warnings-as-errors", str(harness),
                            "-o", str(executable)], check=True, timeout=90)
            completed = subprocess.run(
                [str(executable), str(sleeping)], capture_output=True,
                text=True, check=True, timeout=15,
            )
            self.assertIn("PASS: timed-out native Process", completed.stdout)


if __name__ == "__main__":
    unittest.main()
