# Freshly re-scan generated PDFs before opening (opener-0318)

`scan-and-open.py` now provides a dedicated, optional
`scan_and_open_generated_copy(saved_pdf_path, offer)` entry point for a future
Maximum sanitized-copy UI. It requires an authentic `SanitizedCopyOffer`
object and validates its passive raster-only PDF again. The caller first
saves the offered bytes as a user-selected local PDF; it does not supply
a PDF-originated pathname or let the converter initiate an opening.

Before scanning, the entry point **binds the exact saved file bytes to the
generated output** using the same file fingerprint as the installed
scanner. It refuses any mismatch. It uses the actual installed ClamAV
binary, a snapshot of the active Built-in scan limits, and the existing
cross-process scan slots. It checks the local signature database age and
completeness immediately before scanning.

Unlike a normal scan request, generated output **always runs a new ClamAV
scan**, even when the identical digest has a clean-cache entry. The
existing mandatory full-PDF scan options, fail-closed ClamAV verdict
parser, before/after byte-and-identity verification, intended browser
selection, quarantine retention, and verified launching are reused
unchanged. The generated output can be opened *only* after that
fresh scan and all original handoff checks succeed.

Malware, incomplete results, warnings, timeouts, stale signatures,
changed files, unsupported formats, missing dependencies and other
failures block opening; no failed generated output is authorized.
Ordinary `scan_and_open` continues to use its existing cache and
configuration and is not forced into new scans.

CI covers a deliberately prepopulated clean cache, actual scanner
command arguments, launch ordering, infected/incomplete/timeouts,
file replacement, signature failures, bad offers and ordinary-cache
compatibility on Linux and macOS. macOS additionally compiles the
native CoreGraphics conversion worker and drives a real rasterized PDF
through the generated-copy scan gate (with ClamAV simulated in tests).

**Deployment boundary:** Maximum protection is still non-selectable,
and a native Save/Scan/Open UX remains a separate integration task.
This adds an executable, callable gating path, not a claim that every
future Maximum workflow is already wired up. The deployed Built-in
scanner, scanner defaults, cache policy for ordinary files, user
preferences, signature updates and quarantine remain unchanged.
