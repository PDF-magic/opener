# Protection exception reason record (opener-0348)

**Exceptions remain unsupported.** The security decision established by
[PR #229](https://github.com/PDF-magic/opener/pull/229) is unconditional:
neither users nor callers can exempt PDFs, files, sources, applications, or
profiles from the installed ClamAV gate. Therefore there is no approved
exception whose individual justification can be recorded.

For reporting callers that need a machine-readable reason, the immutable
`EXCEPTION_REJECTION_REASON` records only the **policy reason for refusing an
exception**:

- `reason_code`: `mandatory_protection_no_exceptions`
- `reason`: the canonical, fixed policy message
- `disposition`: `unsupported`
- `exception_granted`: `false`

`record_exception_rejection_reason(request)` returns that same immutable
policy-level reason without inspecting or retaining the proposed request.
`request_protection_exception(request)` continues to raise
`ProtectionExceptionNotSupported`; the rejection carries a read-only
`reason_record` for a caller that catches it. No exception is granted.

**Privacy and scope:** No per-file exception history, user-provided
justifications, filenames, source paths, timestamps, database writes,
allowlists, approval workflow, configuration switch or PDF opening
authorization is created. A detached document representation cannot mutate
the canonical reason. This is a recorded **rejection rationale**, not an
exception approval and not an event audit. If actual exceptions were ever
approved in the future, capturing their individual justifications would
require a new, separately authorized security design and policy decision.

The existing [scanner-failure separation PR #230](https://github.com/PDF-magic/opener/pull/230)
uses the same canonical refusal message, but owns its distinct reporting
contract. This implementation does not change that PR, the installed scanner,
current protection selection, quarantine, cache, signature freshness,
PDF handoff or user preferences.

The dedicated Linux/macOS CI verifies immutable policy-reason metadata,
hostile opaque requests, refusal to grant exemptions, and a real existing
scanner gate that blocks malware despite a forged exemption label.
