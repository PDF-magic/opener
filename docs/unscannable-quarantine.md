# Unscannable PDFs must retain macOS quarantine (opener-0817)

A file that ClamAV cannot conclusively scan must **remain quarantined and
unopened**. This includes scanner engine failures, scan timeouts, heuristic
limit detections, ambiguous or incomplete output, and empty files rejected at
admission. A zero exit code is **not** sufficient when ClamAV reports skipped
content or warnings.

The installed scan gate already rejects these outcomes before reaching its
legacy `remove_quarantine` compatibility hook, which is intentionally a no-op
and never strips `com.apple.quarantine`. The separate opener-0814 audit
inventories removal call sites. This task adds direct regression coverage for
**unscannable files** instead of changing the existing policy or introducing a
new metadata-mutating path.

Run `PYTHONPATH=. python3 tests/general/unscannable-quarantine.py -v`.
On Linux, the tests verify the real scanner decision path, refusal to cache
or open, and unchanged synthetic file bytes. On **macOS**, disposable files
are tagged with an actual `com.apple.quarantine` extended attribute and the
test verifies the original value survives scanner errors, incomplete scans,
timeouts and pre-scan rejection. All scanner results are harmless mocks;
there are no real downloaded documents or external applications.

Both Linux `scanner-tests` and macOS `macos-build` CI execute this
regression. Failures must not silently fall back to another application,
release quarantine, create a clean cache record, or mark a document opened.
The tests never change **user customizations**, installed scanner settings
or Gatekeeper policy. A clean verdict also retains quarantine under the
existing opener-0277 coverage.
