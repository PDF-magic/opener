# Opening quarantined PDFs — scoped macOS acceptance test (opener-0820)

The normal PDF Magic Opener native scan gate must **not discard**
`com.apple.quarantine` when opening a clean PDF in the user's verified
destination application. A clean ClamAV result is **not** permission to
disable macOS Gatekeeper or other system controls.

## Automated test

The new [quarantined-PDF opening test](../tests/general/open-quarantined-pdf.py)
creates its own harmless synthetic PDF in a disposable temporary directory.
On **macOS**, it attaches and reads an actual `com.apple.quarantine` xattr
using `os.setxattr` and `os.getxattr`. Unlike a purely mocked metadata
test, these assertions exercise the operating system's real extended
attribute storage.

The test invokes the **real** `scan_and_open` policy path with a synthetic,
isolated ClamAV result. It replaces only the external scan process and
application launch with test doubles, and records the verified target and
handoff for the same PDF path. It does not alter the system PDF handler,
browser profiles, scanner installation, or user preferences.

Coverage includes:

- A tagged PDF with a completed clean scan reaches the **verified selected
  application** handoff; the original xattr and exact bytes remain intact
  during scanning, destination verification, handoff and after return.
- The same tagged PDF can use a matching *verified clean cache* on a second
  request; no repeat ClamAV scan is made, and the xattr remains unchanged.
- A malicious verdict or scanner timeout does **not** reach the handoff;
  a failed selected-app verification also prevents opening.
- If the native app launcher itself rejects the request, the caller reports
  failure without pretending an opening succeeded or stripping quarantine.
- If PDF bytes change after a clean scan, the integrity gate prevents handoff.
- A portable (non-macOS) case verifies the scan → selected-app verification
  → handoff ordering, even on Linux CI; macOS-only cases skip explicitly
  instead of simulating real xattrs.

The legacy `remove_quarantine` hook remains an inert compatibility function
and is exercised without replacing it. The existing
[quarantine-retention regressions](../tests/general/retain-os-quarantine.py)
and [removal audit](macos-quarantine-removal-inventory.md) remain independent
checks. Neither this task nor the earlier tests clear or rewrite quarantine
attributes for user documents.

## What this does not establish

CI is **not a live Gatekeeper prompt or an end-to-end NSWorkspace GUI launch**.
Launching a real browser could modify system/browser state and depends on
interactive macOS approval and available apps, so the external handoff is
deliberately stubbed. This verifies the scanner-to-approved-launch boundary
and actual quarantine persistence, **not** Gatekeeper's specific user prompts,
Finder double-click behavior or an installed browser's full GUI rendering.
The selected app remains independently verified by the existing native
launcher before a real handoff.

A separately consented, isolated manual acceptance test may use a dedicated
macOS test account and an installed, verified PDF destination; observe the
OS prompt and opening result without clearing xattrs, overriding Gatekeeper
or changing the user's default app. The automated test does not require such
system changes, user PDFs or secrets.

## Run

From the repository root:

```sh
PYTHONPATH=. python3 tests/general/open-quarantined-pdf.py -v
PYTHONPATH=. python3 tests/general/retain-os-quarantine.py -v
python3 tools/audit_quarantine_removal.py
```

The focused test is an explicit step in both Ubuntu `scanner-tests`
(portable behavior and macOS skips) and `macos-build` (real xattrs and all
cases). All existing scanner, quarantine, selected-PDF-app and browser
preferences remain unchanged.
