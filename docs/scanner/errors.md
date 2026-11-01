# Scanner errors and safe recovery (opener-1129)

PDF Magic Opener's installed **Built-in ClamAV** scan gate stops a managed opening
when the scanner cannot start, cannot finish, times out, or fails to return a
complete clean verdict. A scanner error means **the file was not verified as
clean**; it does **not** mean malware was confirmed. Do not open a blocked file
through another application to work around the error.

## Scanner error types

These are the fixed, path-free explanations from the trusted
[scanner failure-response policy](failure-response.md). They are canonical
policy guidance, **not** a promise that every UI surface displays this exact
text; the installed `scan-and-open.py` gate and native alerts may use other
fixed diagnostics. The status is a *terminal* outcome, not an opening permit.

| Failure kind | Canonical status | Fixed policy explanation |
| --- | --- | --- |
| `initializationFailed` | `scanFailed` | The scanner could not start; opening was stopped. |
| `processFailed` | `scanFailed` | The malware scan could not finish; opening was stopped. |
| `incompleteResult` | `incompleteScan` | The malware scan did not confirm a complete scan; opening was stopped. |
| `timedOut` | `scanTimedOut` | The malware scan timed out; opening was stopped. |
| `unknown/untrusted` | `scanFailed` | The scanner failed or its result could not be verified; opening was stopped. |

A nonzero ClamAV exit, a crash, suspicious or skipped content, a warning, an
unexpected scanner response, or output without an explicit usable clean
verdict **blocks opening**. Even exit code zero is insufficient if diagnostic
output makes the scan incomplete. A trusted, non-heuristic malware finding is
reported separately as **malware detected**; a heuristic/unscannable result or
scanner failure must not be mislabeled as confirmed malware. See the
[scan-result status summary](../scan-result-summary.md) and
[unscannable-file quarantine policy](../unscannable-quarantine.md).

## Common prerequisite and input errors

- **ClamAV missing, cannot start, or version unverified:** run the trusted
  installer or [interactive repair](../repair-installation.md) when appropriate.
  The active gate requires a verifiable supported ClamAV **1.4 or 1.5** release;
  an executable merely being present does not prove it can scan.
- **Malware signatures missing, incomplete, or too old:** use the installed
  `update-malware-signatures.sh` workflow. A successful database check must be
  within **48 hours**. The update must succeed and the gate must verify its
  result before any subsequent managed opening; do not forge its timestamp or
  turn off signature checks. See [signature limitations](signature-limitations.md).
- **Selected file missing, unreadable, on an unavailable volume, or not yet
  downloaded locally:** make the original file available to the scanner and
  start a new managed open. A cloud placeholder is not a locally scannable PDF.
  A changed file or symlink is blocked, not trusted based on an earlier result.
- **PDF destination unavailable or rejected:** this is a **separate handoff
  error**, not a malware verdict or proof of a failed ClamAV scan. Check the
  independently verified selected PDF-capable application in
  [browser selection](../select-browser.md); do not disable scanning to bypass
  destination verification.

These are examples of distinct preflight, scanning, and handoff failures, not
an exhaustive list of diagnostic strings. Unexpected exceptions and raw
scanner stderr are not safe troubleshooting text: they may include private
paths. The installed gate's failure formatter uses fixed, path-free
diagnostics for scan requests rather than exposing arbitrary scanner output.

## What to do next

1. Leave the file **unopened and quarantined**. A failed or incomplete scan
   cannot create a verified clean-cache record, remove macOS quarantine, or
   authorize a destination or fallback application.
2. Correct the underlying prerequisite using the normal installer, updater,
   or explicitly authorized repair process. Preserve existing scanner
   settings, browser choices, and other user customizations.
3. Start a **new user-initiated** managed open after resolving the problem.
   There is no automatic retry, safety override, protection downgrade, or
   special exception. The entire ClamAV, signature-freshness, integrity,
   quarantine, and verified-destination gate must succeed again.

The mandatory native failure alert is independent of the optional **Show
Blocked File Notifications** preference, which is off by default. When
enabled, qualifying operational failures can produce one path-free
[failed-scan notification](../failed-scan-notifications.md); notifications
are not a scan verdict or a way to resume opening.

Only the Built-in gate is enforced today. Standard, Enhanced, and Maximum are
currently preview-only/non-selectable; their planned analysis or sanitization
stages do not change these scanner-error recovery steps. This guide changes
**documentation only**, not scanner flags, safety gates, preferences, or
quarantine behavior.
