# Browser extension update delivery (opener-1159)

**Current status: development-only; no production browser extension is published.**
There is no active extension auto-updater, remote update feed, or background
source checkout. Building a ZIP, loading a browser extension, or reloading one
does **not** activate PDF scanning or interception. The toolbar remains
**Not active**, and **Scan PDF** remains disabled. This page describes manual
maintenance only; it does not authorize public distribution.

## Manual developer updates

Use a complete, trusted source checkout and a disposable browser profile.
Do not disable browser signing, enterprise restrictions, or security controls.
Follow the [development installation guide](browser-extension-installation.md)
for first-time loading and browser-specific verification.

- **Chrome, Chromium, Brave, Arc, Vivaldi, Edge and Opera:** run
  `cd extensions/webextension && npm run build`. Reload the **same**
  unpacked `extensions/webextension/dist/` directory through the browser's
  extensions page. A ZIP may be used to transfer the built files, but extract
  it first and load the directory containing `manifest.json`; a ZIP or CRX
  is not assumed to be directly installable. Rebuilding on disk alone does
  not reload the running extension.
- **Firefox:** run `cd extensions/webextension && npm run package:firefox`.
  Reopen `about:debugging#/runtime/this-firefox` and load the temporary
  add-on from `extensions/webextension/dist/firefox/manifest.json`.
  Temporary add-ons disappear when Firefox restarts. The generated unsigned
  ZIP and `example.invalid` Gecko ID are development placeholders, not a
  persistently installable signed XPI. Do not disable Firefox signature
  enforcement. A separately reviewed, correctly identified and signed
  release would be required for persistent direct distribution.
- **Safari:** the extension is embedded in `PDFMagicOpener.app` as
  `PDFMagicOpenerSafari.appex`; rebuilding shared WebExtension assets does
  not update the installed extension. Manually install a trusted replacement
  host app containing the embedded extension, using appropriate Developer ID
  signing and notarization for distribution outside an application store.
  Safari users control enabling it in **Safari Settings → Extensions**.
  Do not silently enable the extension or install an unsigned CI artifact.

Keep the browser profile and extension identity stable when reloading. Do not
remove/reinstall or reset a profile merely to update: doing so can discard
saved preferences and permission choices. If an extension receives a different
ID, treat it as a distinct installation and stop rather than assuming state
was migrated. Verify **Not active** and disabled **Scan PDF** after every
manual reload or host-app replacement.

## Version, identity, and scanner-safety requirements

1. Follow the [release version scheme](release-versioning.md) when preparing
   an update. Keep the shared WebExtension manifest, package version, and
   applicable macOS version/build numbers consistent. Keep intended browser
   IDs and the Safari containing-app identity stable. Review release notes,
   permissions, native-messaging compatibility, and configuration changes.
2. Rebuild and run manifest, package, mocked-runtime, and real-browser upgrade
   tests. Verify the exact installed artifact and observed browser ID against
   native-messaging host allowlists before enabling any future integration.
   Never grant new origins or permissions as an unintended update side effect.
3. Existing `runtime.onInstalled` observation in
   [`src/extension-updates.js`](../extensions/webextension/src/extension-updates.md)
   records an update event only when subscribed to; it is **not a delivery
   mechanism**, is not active in the packaged inert background, and cannot
   authorize a PDF open or modify stored settings.
4. Preserve browser storage, optional permission decisions, private-browsing
   exclusions, the selected PDF destination, and native app preferences.
   Incompatible changes need a separately reviewed, reversible, tested
   migration. On a failed or interrupted manual update, stop, verify the
   prior trusted build and state, and do not silently downgrade, reset data,
   bypass browser restrictions, or claim that unscanned PDFs are safe.
5. The native macOS application follows its separate
   [upgrade process](upgrade-process.md). ClamAV engine and
   [malware-definition updates](scanner/signature-update-process.md)
   are independent. No browser extension update may change quarantine,
   signature freshness, file-integrity checks, the selected opener, or the
   authoritative native **scan-before-open** gate.

**NOT RELEASE READY:** no production extension release or automatic update
channel is configured. Any future signed direct-download release requires its
own approved packaging, distribution, installed-upgrade and rollback checks;
this document does not implement or enable such a system. A successful CI
build or archive ZIP alone is not evidence of safe end-user installation.
