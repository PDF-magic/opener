# ClamAV signature update process (opener-1127)

PDF Magic Opener installs a local **ClamAV** signature database and updates it
with **FreshClam**. These updates are separate from scanning an individual PDF:
an update never accepts a document path, uploads a PDF, changes the selected
PDF application, or authorizes a file to open.

## Automatic and manual updates

The installer configures the per-user `local.studio.pdf-malware-signatures`
LaunchAgent to check for signatures **every four hours while logged in**.
This is a scheduled *check*, not a promise that new signatures are always
available or that a particular update will succeed.

In **Preferences → Updates**, choose **Check for Updates Now** to compare
published ClamAV `main` and `daily` revisions with the installed revisions
without downloading them. If the comparison cannot be verified, it reports an
unknown result. Choose **Update Signatures Now** to invoke the installed
FreshClam updater. Both actions require an explicit click; neither changes the
four-hour LaunchAgent schedule or user preferences.

From a checkout, the corresponding manual update command is:

```sh
bash update-malware-signatures.sh
```

Run this only on a properly installed macOS system with its existing ClamAV
configuration. The updater uses the installed `freshclam.conf` and its known
local FreshClam executable; it does not take document arguments. An automatic
and a manual update use the same guarded process.

## How an update is published

1. Acquire the exclusive update lock. A concurrent update cannot modify the
   database; unsafe or unrecoverable locks fail rather than race.
2. Atomically record `signatures/last-attempted-update`. Copy the existing
   signature database into a private staging directory on the same filesystem.
   FreshClam writes **only to staging**, not to the active database.
3. Run FreshClam using the installed configuration. After an unsuccessful
   invocation, retry at most **once** after a brief pause; signal termination is
   not retried. Detect incomplete downloads and reject unsafe file types,
   ambiguous, missing, or empty required `main` and `daily` databases.
4. Validate the staged definitions using the installed ClamAV scanner and a
   local benign test probe. A successful FreshClam exit alone is not enough.
5. Only after validation, write `signatures/last-successful-update` in staging
   and promote the complete staged directory into place. Retain the previous
   usable database as a rollback copy during promotion. Failed or interrupted
   attempts preserve existing definitions, including custom signatures, and
   do **not** advance the last-successful timestamp.

Do not manually overwrite the live signature files or remove the update lock
to force publication. A lock left by an interrupted update is recovered only
when the updater can verify it predates a reboot.

## Monitor results and recover from failures

**Preferences → Updates** shows the last recorded success, attempt, failure,
and an indeterminate **Signature update in progress** indicator when the
installed updater is active. It cannot display a reliable download percentage.
A failed update records a sanitized reason such as `freshclam-error`,
`updater-unavailable`, or `incomplete-download` instead of exposing raw
FreshClam logs or document contents. Invalid, missing, or stale status records
mean the result cannot be verified.

To inspect the attempted and successful timestamps without running an update:

```sh
python3 "$HOME/Library/Application Support/Studio/allow-and-open/signature_update_status.py"
```

The command prints `lastAttemptedUpdateUtc` and `lastSuccessfulUpdateUtc`
as UTC timestamps or `null`. An attempted update is **not** evidence that it
succeeded. On failure, inspect the sanitized warning in Updates; verify that
ClamAV and the installed updater are available, that the configured network
can reach its update sources, and then retry using **Update Signatures Now**
or the next scheduled check. Do not bypass a lock or copy unverified
definitions into place. A second failure remains a failure.

## Scan safety remains independent

The opener checks the required `main`/`daily` databases and the recorded
successful signature check against its **48-hour** freshness requirement
before each managed file scan, including cache hits. Missing, stale, or
unverifiable definitions **block managed opening**. Neither an update attempt,
a successful update indicator, nor a manual settings choice overrides the scan
gate, file-integrity checks, quarantine, or destination verification.

The **90-day clean-scan cache** is distinct: previously scanned, unchanged
content may still reuse its verified clean result when the other mandatory
checks pass. Installing newer signatures does **not automatically rescan**
an unchanged cached document. A clean ClamAV result never guarantees a safe
document. See [antivirus signature limitations](signature-limitations.md)
and [macOS security controls](../macos-security-controls.md) for these
boundaries.

This page documents the installed process; it changes no update interval,
FreshClam options, scanner flags, signatures, preferences, or opening policy.
