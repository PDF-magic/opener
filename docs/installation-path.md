# Install PDF Magic Opener from a trusted source checkout (opener-1157)

**Current installation path:** the native macOS scan-gated PDF handler can be
installed from a **complete, trusted source checkout**. This is a source-based,
per-user installation, **not** a downloadable, signed and notarized public
installer. No production browser extension or public macOS installation
package is currently offered. Do not treat CI-built unsigned ZIPs as
ready-to-install releases.

## Prerequisites and limits

- Use **macOS 13 (Ventura) or later** with Python 3 and Apple's Xcode command
  line tools. If the compiler is missing, run `xcode-select --install` and
  retry after the tools are installed.
- The existing **Allow and Open** Finder Quick Action must already be at
  `~/Library/Services/Allow and Open.workflow/Contents/document.wflow`.
  The installer checks for this file and **stops** if it is absent. Therefore
  this source route is **not a self-contained clean-Mac installer**; no
  installation procedure for provisioning a missing Quick Action is promised.
- Provide a compatible installed **ClamAV** engine, or have **Homebrew**
  available for optional ClamAV installation. Missing ClamAV provisioning
  requires a terminal and explicit `INSTALL` consent; Homebrew itself is
  never installed automatically. Brave is **optional**, not an installer
  prerequisite. A verified PDF-capable destination is required before opening.
- Use a complete checkout obtained from a source you trust. Do not execute
  an isolated download of the installer script or use `sudo` / root.
  Review the revision and installation changes before proceeding.

See [installation prerequisites](installation-prerequisites.md) and
[ClamAV installation consent](clamav-install-consent.md).

## Install the native scan-gated PDF handler

From Terminal, as the ordinary macOS user, at the **root of the trusted
checkout**:

```sh
bash install-allow-and-open.sh
```

The installer runs the read-only prerequisite checks first, then uses its
existing verified staging, rollback, ClamAV, signature-update and PDF-handler
registration logic. When ClamAV is absent, it displays the intended Homebrew
command and asks for consent instead of silently installing a package.
Follow any separate system prompts only after reviewing their purpose;
declining consent or failing a prerequisite is **not a successful install**.
Installation does not silently erase saved PDF/browser selections, custom
Finder actions, existing scanner configuration or signatures.

On success, the native scan-gated application is installed as
`~/Applications/PDF Magic Opener.app`. This is distinct from the
`PDFMagicOpener.app` **SwiftUI development/preferences build** produced by
Xcode, and from inactive browser-extension scaffolds.

## Verify before using

1. Require the installer to exit successfully. From the same source checkout,
   `python3 scripts/migration_state.py status` is a read-only migration
   check. A `partial` state is **not** a completed installation.
2. Check the intended macOS PDF association using the installed
   `~/Library/Application Support/Studio/allow-and-open/pdf-handler-status.py`
   or the General settings status. Do not silently change an association
   that the user deliberately selected.
3. Open a **trusted, harmless local PDF** with **Open With → PDF Magic Opener**
   or the existing **Allow and Open** Finder action. If configured as the PDF
   default, a Finder double-click also uses the scan gate. Verify it opens
   only after a clean, current ClamAV scan and validated handoff; a failed,
   stale, blocked, changed, or unscannable document must remain blocked.

The native handler protects **local files passed through its entry points**;
it cannot guarantee inspection of browser inline/embedded PDF viewers.
Do not disable Gatekeeper, remove quarantine, weaken scanning, or bypass a
missing prerequisite to complete installation. For failures, consult
[troubleshooting](troubleshooting.md) and the confirmed
[repair procedure](repair-installation.md), rather than resetting preferences.

## Public distribution is a separate prerequisite

A public-installation path still requires independently verified Developer ID
signing, notarization, applicable stapling, Gatekeeper and clean-Mac testing,
and a published trusted downloadable artifact. The
[release gate](release-gate.md) and
[browser distribution audit](browser-extension-distribution.md) currently
**do not authorize** a production package or store installation.
The [browser extension installation guide](browser-extension-installation.md)
covers **development-only** loading, not an alternative to the native scan
gate. Do not instruct users to sideload unsigned release candidates.
