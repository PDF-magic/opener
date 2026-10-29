# Scanner failure response policy (opener-0255)

This is the response **contract**, not a replacement ClamAV engine, profile
selector, or new scanner-error detector. The installed `scan-and-open.py`
remains the only authority to scan, verify, remove quarantine, and launch a
file. No profile, browser, or user setting can override a scanner failure.

| Trusted failure | Canonical result | Response |
| --- | --- | --- |
| Scanner could not initialize | `scanFailed` | Deny opening; explain that scanning could not start |
| Scanner process crashed, returned an error, or gave no usable verdict | `scanFailed` | Deny opening; explain the scan could not finish |
| Scan returned no complete, trustworthy clean verdict | `incompleteScan` | Deny opening; explain that scanning was incomplete |
| Scanner exceeded the allotted time | `scanTimedOut` | Deny opening; explain the timeout |

All responses retain quarantine, prohibit a clean-cache entry, prohibit
destination or fallback handoff, prohibit manual overrides, and do **not**
automatically retry or silently continue. A new scan can only proceed after a
separate user-initiated attempt with working scanner prerequisites; it must
pass the full existing safety gate. The user-facing explanation is selected
from fixed, path-free messages, never arbitrary stderr or a document path,
and failure is never presented as confirmed malware.

An unknown or malformed failure category is treated as `scanFailed`, not
as `clean`. The module `scanner_failure_policy.py` defines this guidance
for trusted categories only; it does not classify untrusted process output
or grant file-opening permission. The broader detection-status response
matrix is scoped to opener-0253.

The installed scanner already fails closed on nonzero exits, missing clean
output, warnings, and timeouts. The dedicated CI regression exercises those
existing gates to verify that none can cache a clean result, remove
quarantine, or launch the selected or fallback application.
