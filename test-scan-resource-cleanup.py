#!/usr/bin/env python3
"""Verify native scan stderr pipes close on both completion and failures."""
from pathlib import Path
import subprocess
import tempfile

source = Path(__file__).with_name("brave-pdf-opener.swift").read_text()
marker = "@main\nstruct PDFMagicOpenerEntry {"
assert marker in source, "Cannot isolate native helper from app entry point"
assert "let failure = withScanErrorPipe" in source, "Native scans must use cleanup wrapper"

swift = ("import Darwin\n" + source.split(marker)[0] + "\n"
         + Path(__file__).with_name("scan-progress-view.swift").read_text()
         + "\n" + (Path(__file__).parent / "PDFMagicOpenerApp" / "ScanProgressPreference.swift").read_text().replace("import Foundation\n", "")
         + """
enum SimulatedFailure: Error {
    case launch
}

func expectClosed(_ descriptor: Int32) {
    errno = 0
    guard fcntl(descriptor, F_GETFD) == -1 && errno == EBADF else {
        fatalError("Temporary scan pipe descriptor \\(descriptor) is still open")
    }
}

let cleanDescriptors = withScanErrorPipe { pipe in
    (pipe.fileHandleForReading.fileDescriptor, pipe.fileHandleForWriting.fileDescriptor)
}
expectClosed(cleanDescriptors.0)
expectClosed(cleanDescriptors.1)

var failureDescriptors: (Int32, Int32)?
do {
    try withScanErrorPipe { pipe -> Void in
        failureDescriptors = (pipe.fileHandleForReading.fileDescriptor,
                              pipe.fileHandleForWriting.fileDescriptor)
        throw SimulatedFailure.launch
    }
    fatalError("Simulated launch failure was unexpectedly ignored")
} catch SimulatedFailure.launch {
    // The wrapper must close both ends before the exception escapes.
}
guard let failureDescriptors = failureDescriptors else {
    fatalError("Missing failed-launch descriptors")
}
expectClosed(failureDescriptors.0)
expectClosed(failureDescriptors.1)

for _ in 0..<12 {
    var descriptors = (Int32(-1), Int32(-1))
    let failedScan = withScanErrorPipe { pipe -> Bool in
        descriptors = (pipe.fileHandleForReading.fileDescriptor,
                       pipe.fileHandleForWriting.fileDescriptor)
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/false")
        process.standardError = pipe
        process.standardOutput = FileHandle.nullDevice
        do {
            try process.run()
            pipe.fileHandleForWriting.closeFile()
            _ = pipe.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            return process.terminationStatus != 0
        } catch {
            return true
        }
    }
    guard failedScan else { fatalError("Expected unsuccessful scanner process") }
    expectClosed(descriptors.0)
    expectClosed(descriptors.1)
}
print("PASS: temporary native scan pipe handles close after errors and failed scans")
""")

with tempfile.TemporaryDirectory(prefix="opener-resource-cleanup-") as directory:
    root = Path(directory)
    test_source = root / "cleanup-test.swift"
    binary = root / "cleanup-test"
    test_source.write_text(swift)
    subprocess.run(["xcrun", "swiftc", str(test_source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)
