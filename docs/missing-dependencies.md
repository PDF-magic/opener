# Missing protection dependencies — response policy (opener-0256)

This is a **declarative fail-closed contract**. It does not detect or install a
dependency, activate a protection tier, change scanner commands, or grant an
exception to the existing ClamAV and verified-opening gates. Standard, Enhanced
and Maximum remain non-selectable.

When a **required** protection component is missing:

- Stop the request. Do not launch the PDF, clear quarantine, cache a clean
  result, switch to a fallback destination, silently downgrade protection, or
  allow a manual safety override.
- Show a fixed, actionable and path-free warning. Never copy raw stderr,
  private file paths or PDF contents into the policy message.
- Return a terminal non-clean status: missing scanner, signatures, or verified
  handoff means scanFailed; missing required file-integrity, structure or
  isolated-behavior inspection means incompleteScan. Neither status permits
  opening and neither is a claim that malware was detected.
- Do not retry the same failed request automatically. After restoring the
  dependency, a *new* request must pass all of the normal checks again.

The immutable response table in missing_dependency_policy.py covers every
PolicyControl from protection_policy_definitions.py, plus a generic denial for
unknown or untrusted controls. Only a trusted, effective **required** control
should be passed to this response policy: simply listing a future *optional*
check does not make it active or required. No inactive profile is selectable.

**Existing enforcement:** scan-and-open.py already refuses to scan/open when
ClamAV is absent, signatures are missing or stale, or an inspection is not
verifiably clean. The regression tests exercise actual missing-binary and
missing-signature preflight behavior without permitting quarantine removal or
launch. The planned structure/behavior controls are not implemented. Future
integration must verify their availability and connect failures to this
response before those tiers can become selectable.
