# Browser download monitoring: protection and limits (opener-0736)

The **Browsers → What monitoring can and cannot prevent** section explains
three distinct conditions to prevent users from assuming that an opt-in
preference means their downloads are being protected.

## What it does today

**Nothing to browser downloads yet.** The monitoring preference saves the
user's choice; it does not grant browser permissions or establish a scanner
connection. The WebExtension background entry point remains inactive, and
the native host handshake is transport-only with `scanAvailable: false`.
Therefore monitoring cannot yet intercept, scan, quarantine, block, warn
about, or delay a browser download or automatically opened file. Its
per-browser status and connection-health displays are deliberately
non-affirmative.

## What a future verified integration might prevent

**Only after separate implementation, consent and authentication**, a
browser-download integration could pass a *fully downloaded, supported*
file to the native scanner, enforce verified scan results, and refuse
a **PDF Magic Opener handoff** on detected malware, incomplete scans,
scan failures or unavailable protection. The existing installed native PDF
opener independently scans files when they are opened **through that opener**;
the future browser workflow is not a substitute for this existing gate.

A downloaded file's browser-provided filename, MIME type, success banner,
saved monitoring preference, registered host, or transport-only handshake
cannot establish a trustworthy clean verdict. The future coordinator
must independently enforce ClamAV, integrity, freshness, and complete
scan-before-handoff checks; nothing here adds that coordinator.

## What it cannot guarantee

Monitoring is not an operating-system-wide opening gate. Unless an
opening path is separately integrated with verified enforcement, it
cannot prevent browser built-in PDF previews, automatic browser opening,
download-history openings, Finder openings, third-party applications,
or other system handlers from accessing a file. It cannot undo an open
that has already happened, guarantee detection of every malicious file,
or equate merely showing a warning with blocking a file.

The explanatory section is read-only. It does not change notification
choices, browser monitoring opt-in, native scan enforcement, PDF
destinations, installed browser discovery, extension permissions, or
any other saved customization.

CI runs `tests/general/download-monitoring-limits.py`, which confirms
the visible accessibility-labeled explanation covers both capabilities
and limits, does not add executable controls, preserves existing
download-settings options, and does not claim active browser scanning.
