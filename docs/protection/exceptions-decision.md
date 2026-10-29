# Protection exceptions: unsupported (opener-0342)

**Decision — Exceptions: unsupported.** The PDF Magic Opener does not permit
exceptions to mandatory protection, whether configured per file, folder, file
extension, source/download origin, destination application, signer, or protection
profile. No user or administrator protection allowlist, override switch, or
"open anyway" bypass is offered. This applies to the installed **Built-in**
ClamAV gate and all **planned** Standard, Enhanced and Maximum levels. Any
future exception mechanism would need separate security analysis and
authorization; this task does not introduce one.

The narrow contract in \`protection_exception_policy.py\` publishes the
immutable support decision and an always-rejecting exception-request API,
without inspecting potentially sensitive paths or user-supplied payloads.
Preferences → Protection presents the unsupported status as accessible,
read-only information. It is **not** a preference, scanner option, exception
registry, additional parser, or new way to open a PDF.

A legitimate, verified **cache** hit for the *same current policy*, source
content, scanner version and signature database is not an exception: it
reuses a previously clean result within the installed security rules. An
optional, independently verified destination **fallback** is an application
selection, not a malware-scan waiver; it still requires a verified clean
scan and correct file integrity. The separate Maximum generated-copy
entrypoint requires a new scan even when identical bytes have been cached.

This decision does not change the mandatory scanner, failure disposition,
quarantine, signature refresh, file identity, cache handling, PDF handoff or
user application preferences. An infected, incomplete, unsupported or
changed file must still be blocked, regardless of any caller-provided
descriptive protection-level metadata.

The \`test-protection-exceptions-decision.py\` regression checks the
decision contract, attempted changes and hostile exception requests,
read-only accessible UI, scanner invariants and a real mocked-infected
scan that blocks despite an attempted exempt protection-level label.
The existing CI runs these tests and compiles the macOS app.

## Review existing exceptions (opener-0349)

Preferences → Protection → **Protection exceptions** now provides a read-only
**Review existing exceptions (0)** disclosure. Opening it shows **Existing
exceptions: none**, explains that no approved exceptions can be saved, and
clarifies that refused requests are not saved as exception entries. The zero
count represents the immutable unsupported-exceptions policy, not a query of
private files, request records, or user preferences. No list of sensitive file
paths is created.

Expanding or collapsing this information is a local presentation state only.
It does not create, edit, delete, approve, or persist an exception, nor does
it touch the scanner, cache, quarantine, selected PDF application or saved
protection preview. The `test-protection-exceptions-review.py` regression
is run by CI; the macOS build verifies the native view still compiles.
