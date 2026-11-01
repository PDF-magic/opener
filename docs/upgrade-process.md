# Upgrade PDF Magic Opener (opener-1130)

This guide covers **upgrading an existing native macOS PDF Magic Opener installation**
from a complete, trusted source checkout. The **Updates** settings page reports
version and signature-update status; it is **read-only**, not an in-app application
updater. ClamAV malware-definition updates are separate from application upgrades.

## Before upgrading

1. Use **macOS 13 (Ventura) or later**, and obtain a **complete, trusted**
   checkout of the version you intend to install. Review that version's changes.
   Do not execute an installer copied in isolation from an unverified source.
2. Check [installation prerequisites](installation-prerequisites.md): Python 3,
   Apple command-line tools, the existing **Allow and Open** Finder Quick Action,
   and a supported ClamAV installation or available Homebrew provisioning route.
   Install missing Xcode command-line tools with `xcode-select --install`.
3. Preserve your own backup of important custom settings and PDF-handler
   choices before changing versions. Do not delete the installed support
   directory, FreshClam configuration, signature database, Finder Quick Action,
   or saved browser preferences to prepare an upgrade.
4. Finish any active scans first. Run the upgrade **as your normal macOS user,
   never with sudo or as root**.

## Install the new version

From the root of that complete checkout, in Terminal, run:

```sh
bash install-allow-and-open.sh
```

The existing installer diagnoses prerequisites before changing installation
state, stages the replacement scan-handler application, verifies managed
components, migrates compatible update-agent and Finder integrations, checks
the PDF handler, and records a completed migration only after those steps
succeed. It preserves the previous working app and managed files for rollback
if migration fails. See [failed-upgrade preservation](failed-installation-preservation.md)
and [migration status](installation-migration-state.md).

An already detected compatible ClamAV installation is **not upgraded or
reinstalled** by this command. If ClamAV is missing, the installer discloses
`brew install clamav` and requires an interactive `INSTALL` confirmation;
declining or running unattended stops that installation path. The installer
does not install Homebrew or silently elevate privileges. An unsupported or
unhealthy scanner remains blocked by the existing scan gate.

Existing selected PDF browser/fallback preferences, FreshClam user settings,
signature databases, and unrelated customized Finder actions must not be
reset merely to upgrade. A compatible Finder action can be migrated while
preserving its original backup; a customized unrecognized action is left
untouched. Changes to the macOS default PDF handler require the installer's
separate consent and verification; upgrading is not authorization to silently
take back a default that the user changed.

## Verify the upgrade

1. Require the installer to exit successfully; a started or interrupted
   upgrade is **not** a completed installation. From the same checkout,
   `python3 scripts/migration_state.py status` is a read-only way to inspect
   the migration journal: expect `complete` for a successful recorded run;
   `partial` requires investigation and a safe retry.
2. Verify the effective PDF handler using the installed
   `"$HOME/Library/Application Support/Studio/allow-and-open/pdf-handler-status.py"`
   command or the General settings status. Check that the handler matches
   **your intended association**; do not silently reassign it.
3. In **Settings → Updates**, review the displayed version and the last
   attempted/successful ClamAV definition-update times. These are historical
   diagnostics, **not** proof of fresh or valid signatures.
4. Only test native opening with a trusted, harmless local PDF using the
   configured scan-gated application/Finder route. ClamAV version,
   definition freshness (48-hour gate), successful malware scan, file-integrity
   checks, and quarantine still govern every opening. Inline browser PDF
   viewers are **not** automatically protected by this native upgrade.

## If the upgrade fails

A failed or interrupted migration must **not** be treated as a success or
used to bypass scanning. Inspect the error and read-only migration status;
resolve missing prerequisites, unsupported ClamAV, changed/unsafe managed
files, or Finder integration conflicts before retrying the same trusted
installer. The installer attempts to restore the previous working native
handler and managed files; if recovery is incomplete, it retains staging
backups for manual investigation rather than deleting them. A successful
rollback does **not** certify scanner health or authorize PDF opening.

For an explicitly confirmed rerun from a complete trusted checkout, use
[Repair Installation](repair-installation.md) and its `REPAIR` prompt.
Do not manually replace individual scanner binaries or reset preferences to
force an upgrade to succeed.

**Distribution boundary:** the browser WebExtension is currently inactive;
its unsigned development ZIPs and Safari CI build are not production update
packages. See [browser extension distribution](browser-extension-distribution.md)
for the separate signing and store-release prerequisites.
