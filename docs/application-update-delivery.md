# Application update delivery policy (opener-1158)

PDF Magic Opener uses source-based updates for the native macOS app and
scan-gated PDF handler. Manual updates are the default. You can opt in to
background updates from the official repository's `main` branch. There is
no published binary update channel.

The Updates settings pane displays installed application version information.
Its manual update actions concern **ClamAV definitions**, not application
versions. ClamAV engine and signature updates are independent of app updates.

## Enable automatic source updates

1. In Finder, double-click `scripts/installation/automatic-updates.command`
   from a complete trusted checkout. Terminal opens for the setup prompts.
2. Finish any active scans, read the source and schedule, then type **ENABLE**.
   Setup fetches the current commit from the official `main` branch, runs
   the source installer, and enables a per-user LaunchAgent after a successful
   install. The usual installation prerequisites and separate ClamAV consent
   still apply.
3. The LaunchAgent checks daily at 9 a.m. local time. It
   uses a temporary checkout inside the installed support folder and installs
   only when the commit changes. The installed bundle records its source
   commit. The agent retries failures on a later check. Ongoing scans defer
   the update. View results in `~/Library/Application Support/Studio/allow-and-open/repository-update/update.log`.

To turn updates off, open the same Finder action and type **DISABLE**. Do
this before uninstalling the native app.

## Manual source updates

1. Obtain a **complete trusted checkout** from the official
   [PDF-magic/opener repository](https://github.com/PDF-magic/opener).
   Select and review the intended Git commit and its change
   history. Do not execute isolated installer scripts, untrusted forks,
   binary downloads, unsigned CI archives, or files supplied by random mirrors.
2. On macOS 13 or later, check [prerequisites](installation-prerequisites.md),
   preserve a backup of customized settings, and finish any active scans.
   Use the normal user account, **never sudo or root**. From the checked-out
   repository root run:

   ```sh
   bash scripts/installation/install-allow-and-open.sh
   ```

3. Follow the [upgrade procedure](upgrade-process.md) for installer results,
   post-install verification, migration state, safe retry, and rollback. A
   fetched newer checkout alone does not change the installed application.

The installer must preserve saved preferences, the selected PDF destination,
ClamAV configuration and definitions, compatible Finder Quick Actions,
quarantine state, and user decisions about the macOS default PDF handler.
It must not silently replace a compatible ClamAV installation or change
default-app associations without explicit consent.

The scan-before-open gate remains authoritative: require current ClamAV
signatures, a complete clean scan, file-integrity checks, preserved quarantine,
and verified handoff to the chosen opener. A successful application
reinstallation does **not** itself demonstrate scanner health or authorize
opening an unscanned PDF.

## No prebuilt release or signing plan

This source workflow does **not** establish GitHub Releases distribution, a downloadable
prebuilt application, Developer ID code signing, notarization, or any automatic
binary updater. No signing or notarization pipeline is planned here. The source-based
installation procedure is development-only and must not be presented as a
verified production application release.

Unsigned or unnotarized macOS applications can be restricted by **Gatekeeper**
and other platform controls. Do **not** bypass Gatekeeper, disable browser or
system security checks, strip quarantine, or recommend an untrusted binary to
make installation succeed. If installation is blocked, stop and record the
limitation. Signing and notarization would require a separate decision and
security review before public binary distribution; they are not prerequisites
being implemented by this PR.

Git commit SHAs identify source checkouts. The
[build metadata requirements](release-versioning.md) do not define public
releases. The source installer and the opt-in LaunchAgent build directly
from repository source. The distribution audit remains **NOT RELEASE READY**.

## Keep independent update streams separate

- **ClamAV signatures** are maintained by FreshClam and manual definition
  update actions, subject to the existing 48-hour freshness gate. ClamAV engine
  management is also separate. See [signature updates](scanner/signature-update-process.md).
- **Browser extensions** are independent. Current Chromium-family builds use
  manual unpacked reloads; Firefox uses temporary developer loading; Safari's
  extension is embedded in the native app. Current extension packages remain
  inactive and do not scan browser PDFs. See [browser extension
  installation](browser-extension-installation.md). An application update
  must not enable extensions, alter native messaging allowlists, grant
  permissions, or reset browser preferences.

**Failure behavior:** Keep the previous installation and its protections if
the source, installer, or migration is untrusted, blocked, interrupted, or
incomplete. Inspect the migration status and follow the rollback or repair
procedure instead of bypassing security controls. Verify ClamAV and the native
scan gate again before opening PDFs.
