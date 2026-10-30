# Firefox Manifest V3 build (opener-0566)

This directory contains Firefox-only Gecko manifest settings. It is not a
standalone extension, and contains no runtime scripts, host access, browser
permissions, or native messaging.

Run from `extensions/webextension/` with Node.js 20 or newer:

```sh
npm run build
node scripts/build-firefox.mjs
npm test
```

The Firefox build combines the common `manifest.json` (including any later
approved name, description, version, and icon metadata) with `firefox/gecko.json`
to create a complete, deterministic `dist/firefox/manifest.json`. The existing
Chromium `dist/manifest.json` stays unchanged. The same `npm test` command
also builds and checks the Firefox variant independently.

Firefox-specific metadata declares Manifest V3, the Gecko minimum version,
and `data_collection_permissions.required = ["none"]`. The `example.invalid`
ID is an explicitly reserved **development placeholder**, not an approved
publisher identity or a claim of a signed add-on. Replace and register an
appropriate unique ID in a separately reviewed publishing task before
submission to addons.mozilla.org; signing, packaging and installation are
outside this task.

This inactive scaffold never scans a PDF, communicates with a native helper,
opens a document, or changes ClamAV validation, quarantine handling, or the
user-selected destination application. Building a manifest is not a safety
verdict.
