# Concise document-security report (opener-0481)

Use `create_document_security_report(combined_scan_report)` from
`document_security_report.py` to produce a short text summary or a detached
JSON-compatible dictionary from validated `CombinedScanReport` evidence.

The report presents the existing scan status and ClamAV signature evidence
separately from the structural inspection summary. Structural findings are
grouped by their validated handling outcome, and incomplete or not-run stages
remain visible. At most three shortened ClamAV signature names are shown; the
remaining detections are counted. Paths, raw ClamAV output, diagnostics, and
PDF-controlled text are not included.

A non-clean scan status, any ClamAV detection, or blocking/incomplete structural
evidence keeps the report blocked. The summary never says that a document is
safe, and every output includes `authorizesOpen: false` (or an equivalent
text statement). A non-blocking report is not an opening authorization: callers
must continue through the existing installed opening gate, quarantine,
integrity, and verified-handoff checks.

This module formats the already validated combined report. It does not run
ClamAV, parse PDFs, activate the planned Enhanced profile, change saved user
preferences, or modify the installed scan gate.
