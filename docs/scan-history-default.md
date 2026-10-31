# Optional local scan history default (opener-0900)

**Decision: optional, user-visible scan history is off by default.**

A record of previously scanned documents can expose sensitive filenames,
document activity, and scan outcomes to anyone with access to the device.
Do not silently begin recording such a history on installation or upgrade.
Any future user-facing history feature must require an explicit, informed
opt-in before retaining per-document history. Absence of a saved choice
means **off**, not consent. Existing settings must not be silently rewritten.

## Current implementation boundary

The optional scan-history feature, its persistence, and its opt-in or
management UI have **not** been implemented. The Privacy and Logs page
explains this decision but does not offer a nonfunctional toggle or pretend
to have cleared, disabled, or retained a history database.

The existing **90-day clean-scan cache** and **operational scan-request
metadata** are separate from optional user-visible scan history. They
support established scanner correctness and request handling, are already
documented in the README, and are **not** modified by this decision.
Do not disable, relabel, or migrate these mechanisms as a shortcut to
implementing optional history. Their existing retention and failure
behavior remain unchanged.

## Requirements for a future opt-in implementation

- Require affirmative consent before creating optional per-document
  scan-history entries; default to off for new users and missing values.
- Preserve a user's explicit enabled or disabled selection on upgrade;
  neither installation nor an unrelated preferences reset grants consent.
- Provide a clear way to disable and clear optional history and a defined
  retention policy, with separate tests for those behaviors when built.
- Never use history records as evidence that a document may bypass the
  current malware, integrity, signature, or quarantine safety gates.

This task makes the default decision and documents it only. It does not
introduce history collection, change existing caches, create a new
preference key, or alter document scanning and opening behavior.
