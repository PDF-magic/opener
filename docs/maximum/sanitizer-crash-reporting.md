# Report sanitizer crashes independently of malware detections (opener-0324)

The opt-in Maximum sanitizer's existing `offer_sanitized_pdf_copy(pdf_bytes)`
continues to return **an offer or `None`** and does not change the deployed
PDF scan gate. For caller-visible diagnostics, use
`attempt_sanitized_pdf_copy(pdf_bytes)`, which returns a frozen
`SanitizerAttempt` containing exactly one `offer` or `failure`.

`SanitizerFailureReport` distinguishes `sanitizerCrashed`,
`sanitizerTimedOut`, `sanitizerMemoryLimitFailed`,
`sanitizerLaunchFailed`, `sanitizerProcessFailed`, `sanitizerInvalidOutput`,
`unsupportedInput` and `sanitizerUnavailable`. A POSIX worker's
**negative exit status** indicates signal termination and is reported as a
sanitizer crash. A positive nonzero exit is a failed conversion, **not** a
claim about what caused it; a timeout is separate. The memory-limit category
means the fixed budget was exceeded or the supervisor could not verify usage;
it is not a malware verdict. Malformed or incomplete sanitizer output is
rejected, never offered.

The failure report's detached `to_dict()` contains a fixed sanitized
user message, `status="sanitizerFailure"`,
`scanVerdict="notAssessed"` and `permitsOpen=false`.
It does **not** return or fabricate `malwareDetected`, `clean`,
malware signature names, worker stderr, PDF data or file paths. Failures
never permit fallback to the original source or bypass required scanning.

Only the separate verified ClamAV scan can produce a
`ScanResultStatus.malwareDetected` result. This task does **not** modify
ClamAV, scanner notices, cached decisions, quarantine, native preferences,
browser handoff, original PDF files or the non-selectable Maximum profile.
An offered sanitized PDF still has `permits_open=False` and
`needs_separate_scan=True`.

Run `python3 test-maximum-sanitizer-reporting.py -v` along with existing
sanitizer and active-content removal suites in the Linux/macOS CI matrix.
The tests launch an actual POSIX child that terminates by SIGKILL, distinguish
timeouts and nonzero exit codes, verify fixed non-sensitive user messages,
and ensure no forged clean or malware verdict can be constructed.

## Native Maximum failure presentation (opener-0550)

The reusable native scan-progress panel exposes the display-only
updateMaximumSanitizationFailure(from:) hook for future trusted Maximum
callers. It accepts only the bounded, canonical five-field JSON returned by
SanitizerFailureReport.to_dict(): sanitizerFailure status, an exact known kind
and fixed message, scanVerdict=notAssessed and permitsOpen=false.
Untrusted text, source paths, PDF metadata and arbitrary JSON are never shown;
invalid reports receive a fixed verification-failure warning.

The panel displays sanitization failure and its fixed reason, explicitly says
that the malware verdict was not assessed, switches to Attention Required/Close
and hides progress. Separately reported Enhanced findings remain available.
Clearing the notice does not grant opening permission. Maximum remains
nonselectable, and this adapter does not execute conversion, alter the active
scanner, quarantine, user preferences, or source files.

The existing macOS test-scan-progress-component.py harness compiles the native
panel and checks visible blocked state, valid and forged reports, privacy and
layout alongside Enhanced findings. A portable regression compares all native
messages with the canonical sanitizer report.
