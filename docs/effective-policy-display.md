# Inspect the exact effective scan policy (opener-0341)

In **Protection** settings, expand **View exact effective scan policy** to
read a selectable, monospaced JSON representation of the current enforced
policy. The disclosure is collapsed initially, works with keyboard and
VoiceOver, and neither launches a scan nor edits any preferences.

The JSON describes the complete four-field effective policy contract from
`effective_protection_policy.resolve_effective_policy()`: `profile_id` is
`built-in`, `required_checks` are ClamAV scanning, signature freshness,
file integrity and fail-closed opening, `optional_checks` is empty, and
`failure_disposition` is `deny`. The planned Standard, Enhanced, and
Maximum preview cards cannot change these values.

**Exactness boundary:** this is the enforced **policy contract**, not a
particular scan's ClamAV result, whether the installed signature database is
currently fresh, the local scanner binary version, or mutable process-local
timeout budgets. Those request-specific facts cannot be inferred from a
separate Settings process and are explicitly labeled as outside the snapshot.
The UI does not claim to inspect a scan that is underway.

The native text is checked on Linux and macOS by
`test-effective-policy-display.py`, which parses the actual JSON shown in
the view, compares every field with the authoritative Python resolver, checks
profile-selection fail-closed semantics and verifies that the control does
not add scanning or settings side effects. The existing full macOS
application build still compiles the SwiftUI view.

This change does not modify the installed scanner, active protection
selection, target application, signature updates, cache policy, quarantine,
or previously saved profile previews.
