# Browser extension update delivery (opener-1159)

**Current status: development-only; no production browser extension is published.**
There is no active extension auto-updater or store-delivered extension in this
repository. Building a ZIP, loading an unpacked extension, or observing an
update notification does **not** activate PDF scanning or interception. The
toolbar remains **Not active**; **Scan PDF** remains disabled. This policy
defines current behavior and the intended release channels, not permission to
publish an unsigned artifact.

## Current developer installations

- **Chrome, Chromium, Brave, Arc, Vivaldi, Edge and Opera:** rebuild from a
  complete, trusted checkout with `cd extensions/webextension && npm run build`,
  then use each browser's extension management page to reload the *same*
  unpacked directory in a disposable profile. Rebuilding source does not
  silently deliver updates to another browser or an installed store extension.
  Retain the existing browser profile, extension identity and granted/denied
  permissions; do not remove/reinstall or reset the profile merely to update.
  If the browser assigns a different ID, treat it as a distinct extension and
  stop rather than assuming its saved state migrated.
- **Firefox:** rebuild the separate Firefox output with
  `npm run package:firefox`, then reload the temporary add-on from
  `extensions/webextension/dist/firefox/manifest.json` using
  `about:debugging#/runtime/this-firefox`. Temporary add-ons do not persist
  across restarts. The unsigned ZIP and `example.invalid` Gecko ID are not
  a production XPI or a persistent automatic update channel.
- **Safari:** the extension is embedded in `PDFMagicOpener.app`. Rebuilding
  shared WebExtension assets does not update an installed Safari extension.
  A new trusted, correctly signed host-app installation must contain the
  reviewed embedded `PDFMagicOpenerSafari.appex`; Safari users independently
  control enabling the extension under Safari Settings. Never turn it on
  silently or replace the host app with an unsigned CI artifact.

See [development installation](browser-extension-installation.md) for the
browser-specific testing steps. These developer operations are **manual**;
there is no custom polling service, extension self-update download,
unverified remote update endpoint or automatic source checkout installed.

## Future production delivery (not yet enabled)

| Browser/channel | Intended update publisher and delivery | Prerequisite |
| --- | --- | --- |
| Chrome Web Store (Chrome, and supported Brave/Arc/Vivaldi installs) | Upload reviewed new versions through the existing Chrome Web Store listing; the browser/store manages update discovery and installation subject to user, enterprise and browser policy. | Verified publisher account, published ID and installed signed store build. |
| Microsoft Edge Add-ons | Publish separately to the same Edge Add-ons listing/identity; Edge manages installation and updates under its policies, not the Chrome submission automatically. | Edge-specific approval, identity and installed-build verification. |
| Opera Add-ons | Submit and pass Opera review for the existing Opera listing/identity; Opera handles its store update delivery. | Opera publisher approval and browser verification. |
| Firefox AMO (listed) | Submit the Firefox-specific version under its stable, publisher-owned Gecko ID; Mozilla signs and distributes accepted updates through Firefox's add-on update mechanism. | Replace the placeholder ID and obtain AMO review/signing. |
| Firefox AMO (unlisted) | Only an independently reviewed, Mozilla-signed self-distribution and authenticated update arrangement may be used. No such update endpoint or published XPI is configured here. | Real Gecko ID, signing, explicit update-channel design and testing. |
| Safari Mac App Store | Release the signed host app containing the updated Safari extension through App Store review; the Mac App Store updates the host app according to its update settings. | Approved app/extension identities, provisioning, submission and review. |
| Safari Developer ID (outside the store) | Distribute a verified Developer ID-signed and notarized replacement host app through an approved release channel; the user installs the app update. No background Safari or host-app updater is implemented. | Verified app and extension signing, notarization, stapling, release approval and user installation. |

This is **not** a cross-browser shared auto-update feed. A Chrome ZIP is
not an Edge/Opera store submission, a Firefox unsigned ZIP is not a signed
XPI, and the Safari .appex is not a standalone browser download. Store
updates depend on acceptance and may be delayed or disabled by browser,
profile, enterprise policy or user settings. Do not promise immediate
updates, bypass those choices, or claim that any channel is currently live.
See the [distribution/signing audit](browser-extension-distribution.md),
which remains **NOT RELEASE READY**.

## Version, identity, security and recovery requirements

1. Before publishing, follow the [release version scheme](release-versioning.md):
   advance the product `X.Y.Z` in the shared WebExtension manifest, package
   metadata and macOS marketing version as applicable. Maintain the appropriate
   stable store extension/Gecko ID, Safari containing-app identity, and
   version/build-number rules. Publish release notes and review permission,
   native-messaging and configuration compatibility changes.
2. Rebuild and run the existing manifest, package, mocked runtime and
   real-browser upgrade tests. Require store/installed artifact verification,
   channel signing, review and publisher-confirmed identities. Recheck
   [published IDs against native allowlists](browser-extension-distribution.md#check-published-ids-against-native-messaging-allowlists-opener-1154)
   before a production native bridge is permitted; no new origins or grants
   are introduced by an update.
3. Existing update observation in
   [`src/extension-updates.js`](../extensions/webextension/src/extension-updates.md)
   only normalizes explicit `runtime.onInstalled` update events when a future
   integration subscribes. It is **not a delivery mechanism**, is not active
   in the packaged inert background, and does not request permissions,
   clear storage, migrate settings or authorize a PDF open.
4. Preserve browser storage, optional permission decisions, private-browsing
   exclusions, the user's selected PDF destination and native application
   preferences. Any incompatible migration needs a separately reviewed,
   reversible, tested implementation. A failed, paused, disabled or rolled-back
   extension update must never weaken scanner checks or imply that an unscanned
   PDF is safe. If a store version fails, disable the affected integration and
   follow that store's reviewed rollback/review process; do not install a
   lower-version unsigned ZIP or silently reset extension data.
5. The separately installed native macOS handler is updated according to the
   [application upgrade process](upgrade-process.md); ClamAV engine and
   [malware-definition updates](scanner/signature-update-process.md) are
   independent. An extension update cannot replace the native app, alter
   quarantine, bypass signature freshness/file-integrity checks, or automatically
   intercept PDFs. Keep the native scan-before-open gate authoritative.

Only after each channel's real publication and end-to-end installed-update
checks pass can its delivery policy be described as operational. An Actions
green check or a package ZIP alone is not evidence of publication.
