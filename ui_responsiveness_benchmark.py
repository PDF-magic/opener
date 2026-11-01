#!/usr/bin/env python3
"""Opt-in macOS AppKit UI latency benchmark with a non-authorizing test scan child."""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import statistics
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
ENTRY_MARKER = "@main\nstruct PDFMagicOpenerEntry {"
GATE_REFERENCE = (
  'FileManager.default.homeDirectoryForCurrentUser\n'
  '            .appendingPathComponent("Library/Application Support/Studio/allow-and-open/scan-and-open.py")'
)
RESULT_PREFIX = "UI_RESPONSIVENESS_RESULT="
FIELDS = {"heartbeat_delays_ms", "cancel_dispatch_delay_ms",
          "scan_active_at_cancel", "cancel_action_available"}


def percentile(values, fraction):
  if not values or not 0 < fraction <= 1:
    raise ValueError("Nonempty values and valid percentile required")
  return sorted(values)[math.ceil(len(values) * fraction) - 1]


def validate_sample(item):
  if not isinstance(item, dict) or set(item) != FIELDS:
    raise ValueError("Invalid native measurement fields")
  delays = item["heartbeat_delays_ms"]
  if not isinstance(delays, list) or len(delays) < 40:
    raise ValueError("Insufficient event-loop samples")
  for value in delays + [item["cancel_dispatch_delay_ms"]]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
      raise ValueError("Invalid timing type")
    if not math.isfinite(value) or value < 0:
      raise ValueError("Non-finite or negative timing")
  if item["scan_active_at_cancel"] is not True or item["cancel_action_available"] is not True:
    raise ValueError("Scan or Cancel was not active")
  return item


def aggregate(samples):
  if not samples:
    raise ValueError("No measured runs")
  samples = [validate_sample(item) for item in samples]
  delays = [delay for item in samples for delay in item["heartbeat_delays_ms"]]
  clicks = [item["cancel_dispatch_delay_ms"] for item in samples]
  return {
    "scope": "nativeProgressEventLoopWithSyntheticScanChild",
    "measured_runs": len(samples),
    "heartbeat_observations": len(delays),
    "heartbeat_median_delay_ms": round(statistics.median(delays), 3),
    "heartbeat_p95_delay_ms": round(percentile(delays, 0.95), 3),
    "heartbeat_max_delay_ms": round(max(delays), 3),
    "cancel_dispatch_median_delay_ms": round(statistics.median(clicks), 3),
    "cancel_dispatch_max_delay_ms": round(max(clicks), 3),
    "real_clamav_measured": False, "scanner_verdict_measured": False,
  }


SWIFT_DRIVER = r"""
let app = NSApplication.shared
let delegate = PDFOpener()
app.delegate = delegate
app.setActivationPolicy(.accessory)
var heartbeatDelays = [Double]()
var pollAttempts = 0

func heartbeat() {
    let expected = ProcessInfo.processInfo.systemUptime + 0.025
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.025) {
        let late = max(0, (ProcessInfo.processInfo.systemUptime - expected) * 1_000)
        heartbeatDelays.append(late)
        heartbeat()
    }
}

func waitForActiveScan() {
    pollAttempts += 1
    guard pollAttempts <= 160 else { fatalError("Native scan never became active") }
    guard let panel = app.windows.compactMap({ $0 as? ScanProgressPanel }).first else {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { waitForActiveScan() }
        return
    }
    if panel.activeScansLabel.stringValue != "Active scans: 1" ||
       !FileManager.default.fileExists(atPath: __STARTED__) {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { waitForActiveScan() }
        return
    }
    heartbeat()
    let expectedCancel = ProcessInfo.processInfo.systemUptime + 1.6
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) {
        let delay = max(0, (ProcessInfo.processInfo.systemUptime - expectedCancel) * 1_000)
        let active = panel.activeScansLabel.stringValue == "Active scans: 1" &&
                     FileManager.default.fileExists(atPath: __STARTED__)
        let actionable = panel.cancelButton.title == "Cancel" &&
                         panel.cancelButton.isEnabled && panel.isVisible
        guard heartbeatDelays.count >= 40 && active && actionable else {
            fatalError("Native progress did not remain responsive during scanning")
        }
        let report: [String: Any] = [
            "heartbeat_delays_ms": heartbeatDelays,
            "cancel_dispatch_delay_ms": delay,
            "scan_active_at_cancel": active,
            "cancel_action_available": actionable
        ]
        let data = try! JSONSerialization.data(withJSONObject: report)
        print("UI_RESPONSIVENESS_RESULT=" + String(data: data, encoding: .utf8)!)
        fflush(stdout)
        panel.cancelButton.performClick(nil)
    }
}
DispatchQueue.main.async {
    delegate.application(app, open: [URL(fileURLWithPath: __DOCUMENT__)])
    waitForActiveScan()
}
app.run()
"""


def driver_source(gate, document, started):
  """Change only the scan helper path in a throwaway copy of the native handler."""
  source = (ROOT / "brave-pdf-opener.swift").read_text(encoding="utf-8")
  if source.count(ENTRY_MARKER) != 1 or source.count(GATE_REFERENCE) != 1:
    raise ValueError("Native handler injection contract changed")
  source = source.split(ENTRY_MARKER, 1)[0]
  source = source.replace(GATE_REFERENCE,
                          "URL(fileURLWithPath: " + json.dumps(str(gate)) + ")", 1)
  source += "\n" + (ROOT / "scan-progress-view.swift").read_text(encoding="utf-8")
  source += "\n" + (ROOT / "PDFMagicOpenerApp" /
                    "ScanProgressPreference.swift").read_text(encoding="utf-8")
  return (source + "\n" + SWIFT_DRIVER.replace("__DOCUMENT__", json.dumps(str(document)))
          .replace("__STARTED__", json.dumps(str(started))))


def run_once(root, index):
  case = root / ("run-" + str(index))
  case.mkdir(mode=0o700)
  gate, started, document = case / "controlled_scan.py", case / "child.pid", case / "inert.pdf"
  # The test-only scan worker sleeps and never reads, approves, opens or parses the PDF.
  document.write_bytes(b"%PDF-1.4\n% inert UI-only placeholder\n")
  gate.write_text(
    "import os\nfrom pathlib import Path\nimport time\n"
    "Path(" + repr(str(started)) + ").write_text(str(os.getpid()))\n"
    "time.sleep(30)\n", encoding="utf-8"
  )
  swift, binary = case / "harness.swift", case / "harness"
  swift.write_text(driver_source(gate, document, started), encoding="utf-8")
  subprocess.run(["/usr/bin/xcrun", "swiftc", str(swift), "-o", str(binary)],
                 check=True, stdout=subprocess.DEVNULL,
                 stderr=subprocess.PIPE, timeout=90)
  process = subprocess.Popen([str(binary)], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)
  try:
    stdout, _ = process.communicate(timeout=25)
  except subprocess.TimeoutExpired:
    os.killpg(process.pid, signal.SIGKILL)
    process.communicate()
    raise ValueError("Native UI failed to terminate after Cancel")
  if process.returncode != 0:
    raise ValueError("Native UI harness failed")
  reports = [line[len(RESULT_PREFIX):] for line in stdout.splitlines()
             if line.startswith(RESULT_PREFIX)]
  if len(reports) != 1 or not started.is_file():
    raise ValueError("Missing complete native UI measurement")
  result = validate_sample(json.loads(reports[0]))
  pid = int(started.read_text(encoding="utf-8"))
  try:
    os.kill(pid, 0)
  except ProcessLookupError:
    pass
  else:
    os.kill(pid, signal.SIGTERM)
    raise ValueError("Cancel did not terminate controlled scan process")
  return result


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--samples", type=int, default=3)
  args = parser.parse_args(argv)
  if sys.platform != "darwin":
    parser.error("Requires real macOS AppKit")
  if not 1 <= args.samples <= 5:
    parser.error("Expected 1–5 samples")
  try:
    with tempfile.TemporaryDirectory(prefix="pdfmagic-ui-response-") as temp:
      root = Path(temp)
      run_once(root, 0)  # Discard warmup after verifying Cancel.
      samples = [run_once(root, i + 1) for i in range(args.samples)]
      print(json.dumps(aggregate(samples), sort_keys=True))
      return 0
  except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError):
    print("UI responsiveness benchmark failed; no partial measurements.", file=sys.stderr)
    return 1


if __name__ == "__main__":
  raise SystemExit(main())
