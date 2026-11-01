# Native scan-progress UI responsiveness — opener-1085

Run on macOS with Xcode Command Line Tools:

    python3 ui_responsiveness_benchmark.py --samples 3

This **opt-in** benchmark compiles a temporary copy of the existing native
PDF handler plus the real AppKit scan-progress panel. Only in that test copy,
it substitutes a controlled 30-second sleeping scan child for the installed
scanner helper. The child's synthetic PDF path is a placeholder that is not
opened or scanned. The production scanner, installed signatures, quarantine,
browser selection, preferences, user PDFs and opening policy are untouched.

Measurements start only when the real native handler reports an active scan
and the test child is confirmed running. A 25-ms scheduled main-queue
heartbeat measures event-loop callback lateness with the progress panel and
its animation in use. The test also measures the delay before a scheduled
Cancel click, clicks the panel's real Cancel button, and verifies the child
terminated. A warmup is discarded, each run needs at least 40 observations,
and incomplete runs fail without publishing partial results.

Output is path-free JSON reporting median, p95 and maximum heartbeat delay,
Cancel-dispatch median and maximum delay, and sample counts. These values
measure **native UI event-loop scheduling under a synthetic scan workload**,
not physical input latency, frame rendering time, actual ClamAV scanning or
an end-to-end real-PDF opening. No security verdict is inferred. Host load
varies; CI records real macOS measurements without hard speed thresholds.

Portable contract tests run on Ubuntu; the AppKit measurement runs on macOS.
Any real-production ClamAV responsiveness claim requires a separate test
with an authorized, configured scanner. This benchmark cannot approve a file.
