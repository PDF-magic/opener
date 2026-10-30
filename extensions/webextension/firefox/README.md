# Firefox Manifest V3 build (opener-0566)

This directory contains Firefox-only Gecko manifest settings. It is not a
standalone extension. It packages the shared intentionally inert background
entry point using Firefox-compatible MV3 `background.scripts` rather than
Chromium `background.service_worker`. The script has no event listeners,
network access, native messaging or PDF logic; no host permissions are added.

Run from `extensions/webextension/` with Node.js 20 or newer:

```sh
npm run build
node scripts/build-firefox.mjs
npm test
```

The Firefox build combines the common `manifest.json` (including any later
approved name, description, version, and icon metadata) with `firefox/gecko.json`
to create a complete, deterministic `dist/firefox/manifest.json` and
`dist/firefox/background.js`, independently of the Chromium build. The existing
Chromium `dist/manifest.json` stays unchanged. The same `npm test` command
also builds and checks the Firefox variant independently.

Firefox-specific metadata declares Manifest V3, the Gecko minimum version,
and `data_collection_permissions.required = ["none"]`. The `example.invalid`
ID is an explicitly reserved **development placeholder**, not an approved
publisher identity or a claim of a signed add-on. Replace and register an
appropriate unique ID in a separately reviewed publishing task before
submission to addons.mozilla.org; signing, publication and installation are outside this task.

This inactive scaffold never scans a PDF, communicates with a native helper,
opens a document, or changes ClamAV validation, quarantine handling, or the
user-selected destination application. Building a manifest is not a safety
verdict.


## Build an unsigned Firefox extension package (opener-0605)

From `extensions/webextension/`, run:

```sh
npm run package:firefox
npm test
```

The packaging command **rebuilds and validates the Firefox-specific assets**
and writes `dist/firefox-packages/pdf-magic-opener-firefox-<version>-unsigned.zip`.
The archive contains exactly eight approved extension files at its root:
`manifest.json`, `background.js`, `popup.html`, `popup.css` and the
four validated icons. The `browser_specific_settings.gecko` metadata is
embedded in its manifest; the Chromium service-worker manifest is **not**
included. No source modules, nested build artifacts, configuration, user
preferences, keys or other files are packaged.

The ZIP is deterministic from validated inputs, rejects symlinked or
oversized assets, and is written atomically. The existing deterministic,
dependency-free ZIP encoder is reused because the two browser targets need
the same eight filename paths; each browser's **different manifest bytes**
are checked before packaging. CI builds and checks the Firefox ZIP under the
existing WebExtensions test job, independently verifies its archive headers,
exact entries, bytes, Firefox-specific permissions and repeatability, and
checks archive integrity with `unzip -t`.

**Unsigned ZIP, not a signed XPI:** Mozilla requires signing for ordinary
Firefox release installation. This command does **not** request signing,
pretend the development Gecko ID is a verified publisher ID, or publish
to addons.mozilla.org. A production add-on ID and Mozilla signing are
separate prerequisites before user distribution. Firefox's own guidance:
https://extensionworkshop.com/documentation/publish/package-your-extension/

The extension remains intentionally inactive and cannot scan, sanitize or
open PDFs. Packaging changes neither scanner safety nor user customizations.
