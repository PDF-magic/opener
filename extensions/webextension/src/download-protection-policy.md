# Apply configured protection to completed-download scans (opener-0693)

The installed PDF Magic Opener scanner currently supports **only Built-in**
protection: ClamAV scan gate, signature freshness, file-integrity validation,
and fail-closed handoff. The Standard, Enhanced and Maximum cards are **preview
preferences**, not executable policies. Saved `preferredProtectionLevel`
choices must never be treated as a selectable scanning configuration.

`createConfiguredDownloadProtectionCoordinator(trustedCoordinator,
readConfiguration)` is an opt-in, passive adapter around the injected trusted
native coordinator's `submitCompletedPdfDownload(request, policy)` method.
A trusted reader supplies a fresh, **read-only** active configuration snapshot
for every request, with `selectedProtectionProfile` absent (documented
Built-in default) or exactly `"built-in"`. Explicit unsupported, corrupted,
planned or future selections are **rejected**, not silently replaced or
persisted. Preview choices and unrelated user settings are untouched.

The adapter binds the immutable installed effective policy:
`{profileId:"built-in", requiredChecks:["clamav_scan_gate",
"signature_freshness","file_integrity","fail_closed_handoff"],
failureDisposition:"deny"}`. It passes that policy separately from the
exact ID/local-path candidate to an independently authenticated native
coordinator, not directly to the transport-only native messaging host.
A positive request acknowledgment must report `accepted: true` and
`effectivePolicyId: "built-in"`; otherwise the result fails closed. A
selection change, disconnected coordinator or unavailable configuration
also fails closed. A successful result **only acknowledges submission**,
not scanning success, file safety or permission to open.

**Deployment prerequisite:** The native coordinator must enforce the requested
effective policy *itself* and report the effective policy actually applied;
a caller-provided string cannot enforce controls. The current standalone
native messaging host deliberately rejects scan requests until a trusted
coordinator exists. This adapter is designed to compose with the separately
scoped completed-PDF submission boundary (opener-0692) once that prerequisite
is implemented. This PR does **not** activate the background, scanner,
new protection tiers, native host, browser permissions, or any user preference.
The installed scanner's per-request Built-in snapshot, mandatory ClamAV checks,
quarantine, integrity validation and application selection remain authoritative.

The 11 regression tests in `tests/download-protection-policy.test.mjs`
are automatically included by WebExtensions `npm test` in required
`scanner-tests` CI.
