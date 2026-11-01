# What Standard checks (opener-1112)

**Standard is a defined, preview-only protection level.** It is not a selectable
or active scan policy. The installed **Built-in** policy independently enforces
the same four mandatory safety controls listed below; selecting the Standard
card does not switch the scanner into a new mode or change any saved settings.

## Required checks

- **ClamAV malware scan gate** (`clamav_scan_gate`) — A local ClamAV verdict is
  required before a PDF is handed to its configured application. A detected
  threat, scan failure, timeout or missing valid verdict blocks opening; a
  cached clean verdict is usable only under the existing verified cache policy.
- **Signature freshness** (`signature_freshness`) — The malware signature
  database must have been checked within **48 hours**. Stale or unavailable
  signatures block opening, including when a previous clean verdict is cached.
- **File integrity** (`file_integrity`) — Verify the file's bytes and identity
  through scanning or cache use and again before opening. Changed or replaced
  files cannot inherit another file's clean verdict.
- **Fail-closed verified opening** (`fail_closed_handoff`) — Hand off only after
  all applicable mandatory checks succeed. Incomplete, unsafe or unverified
  requests stop without silently changing the selected PDF application or
  stripping the macOS quarantine attribute.

## Optional, planned check

- **PDF structure validation** (`pdf_structure_validation`) — The Standard
  policy definition lists structural parsing as **optional and planned**.
  It is **not active** as an enforced Standard check and does not substitute
  for a clean ClamAV verdict. Separate optional parser components do not make
  Standard selectable.

## Not included

**Isolated behavior analysis** (`isolated_behavior_analysis`) is not a Standard
requirement or optional check. It is a separate planned control for higher
levels, not an inspection promised by Standard.

These lists mirror `protection_policy_definitions.py`. The three proposed
Standard, Enhanced and Maximum profiles are non-selectable for enforcement;
`selectedProtectionProfile = "standard"` is rejected by the effective-policy
resolver rather than silently accepted or downgraded. The existing **Built-in**
gate remains authoritative, including its scanner policy, quarantine handling,
cache validation and user-customized destination application. A clean scan
means no threat was detected, **not** proof that a PDF is safe.
