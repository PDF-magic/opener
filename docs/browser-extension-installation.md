# Install a browser extension (development only)

**Release status: no installable production browser extension is published by this
repository.** The current browser extensions are **inactive development scaffolds**.
Installing or enabling one **does not scan, sanitize, intercept, or open PDFs**.
The toolbar popup should say **Not active**, and **Scan PDF** must remain
disabled. Browser extension installation is separate from installing the
macOS native [PDF Magic Opener](../README.md), whose local-file ClamAV scan
gate works independently of browser extensions.

Use a trusted source checkout and a **disposable browser profile** for the
manual developer steps below. They are *not* instructions to install an
unreviewed extension in a daily-use browser or a release installation. Do not
disable browser signing, system security, enterprise policies, or existing
extensions to make a test install succeed.

## Build the reviewed local assets

Install Node.js 20 or newer. From the repository root:

```sh
cd extensions/webextension
npm run build
npm run package:firefox
npm run validate:manifests
npm test
```

`npm run build` creates the unpacked Chromium-family directory
`extensions/webextension/dist/`. The Firefox command creates the
**Firefox-specific** `extensions/webextension/dist/firefox/` directory and
the unsigned `dist/firefox-packages/pdf-magic-opener-firefox-<version>-unsigned.zip`.
The Chromium upload package can also be generated with
`npm run package:chrome`, producing
`dist/chrome/pdf-magic-opener-chrome-<version>.zip`. These ZIP files are
**review/submission artifacts**, not signed release extensions; for the
developer steps below, load the *directory*, not the ZIP. Generated
`dist/` assets are ignored by Git.

## Chromium-family browsers: load unpacked for a local test

In a **separate test profile** of a supported desktop browser, open its
extension management page:

| Browser | Extension management page |
| --- | --- |
| Google Chrome | `chrome://extensions` |
| Chromium | `chrome://extensions` |
| Brave | `brave://extensions` |
| Microsoft Edge | `edge://extensions` |
| Vivaldi | `vivaldi://extensions` |
| Opera | `opera:extensions` |
| Arc (macOS) | `arc://extensions` |

1. Enable **Developer mode** in that browser's extensions page (if available).
2. Choose **Load unpacked** (Opera may label it **Load Unpacked Extension**).
   Select the *built* `extensions/webextension/dist/` directory, which
   contains the Chromium `manifest.json`; do not select the repository
   root, the Firefox output, or an unopened ZIP.
3. Confirm **PDF Magic Opener** appears in the extension list. Open its
   toolbar popup and verify **Not active** and a disabled **Scan PDF** control.
   Do not grant optional `downloads` access or private-browsing access.
4. If loading is unavailable or blocked by the browser, version, or managed
   policy, record that as a test limitation. Do not bypass the restriction.

These steps describe an **unpacked development test**, not installation from
Chrome Web Store, Edge Add-ons, or Opera Add-ons. Chrome for Testing is used
for the packaged-ZIP automated smoke because some branded Chrome versions
restrict command-line extension loading; the manual management UI and
supported development modes vary by browser. See each browser's compatibility
notes under [WebExtensions](../extensions/webextension/README.md).

## Firefox: temporary developer extension

1. Build the Firefox-specific output above. In a disposable desktop Firefox
   profile, open `about:debugging#/runtime/this-firefox`.
2. Choose **Load Temporary Add-on…**, then select
   `extensions/webextension/dist/firefox/manifest.json` (not the
   Chromium `dist/manifest.json`).
3. Verify the **Not active** popup and disabled **Scan PDF** control without
   granting additional privileges. Temporary add-ons are removed when
   Firefox restarts; reload from the built manifest when testing again.

The generated Firefox ZIP is **unsigned**, contains a development-only
`example.invalid` Gecko ID, and is not a signed XPI. Ordinary release
installation requires a publisher-owned ID and Mozilla signing through AMO,
even for unlisted distribution. Do not turn off Firefox signature checks
to install this development package as a permanent add-on.

## Safari on macOS: enable the app-bundled extension

Safari does **not** load the shared `dist/` directory or a Chromium/Firefox
ZIP. Its extension is bundled as `PDFMagicOpenerSafari.appex` within
`PDFMagicOpener.app`. Use a correctly **signed, trusted host-app build**
installed and launched on a test Mac. Open **Safari → Settings → Extensions**,
find **PDF Magic Opener Safari Extension**, and explicitly enable it. Confirm
the toolbar popup still reports **Not active**. You can uncheck it to disable
the extension again; do not modify someone else's Safari settings.

The unsigned macOS CI archive is **not a signed/notarized public installer**;
it does not prove Safari registration or allow automatic activation. Installing
a production Safari extension requires host-app and extension signing and
appropriate distribution/notarization. An unsigned development test may
require separate explicit Safari developer authorization, **not** a recommended
production installation step. See the
[Safari activation test](../extensions/safari/README.md#safari-activation-acceptance-test-opener-0611)
for manual acceptance details.

## Production stores, verification, and removal

There is currently **no published Chrome Web Store, Edge Add-ons, Opera Add-ons,
Firefox AMO, or Safari release** to install. The
[distribution and signing audit](browser-extension-distribution.md) identifies
per-store review, signing, publishing, and browser verification prerequisites.
Do not infer that a locally built ZIP is store-approved or installable.

For any development test, the expected result is an **inactive** toolbar
popup; never interpret installing/enabling the extension, viewing an inline
PDF, or granting `downloads` permission as an approved malware scan.
The native macOS opener separately checks ClamAV signature freshness, file
integrity, quarantine, and the chosen post-scan application. To use that gate
for a browser-downloaded PDF, save it locally and open the file through the
[installed native PDF handler](../README.md#browser-independent-pdf-opening).
Inline browser PDF viewers may bypass that local-file path.

To undo a developer test, use the browser's extensions page to
**Remove** the unpacked or temporary extension; on Safari, uncheck it under
**Safari → Settings → Extensions**. Do not reset unrelated browser
preferences, disable security controls, or change the macOS default PDF
application as part of extension removal.
