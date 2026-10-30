# Chrome extension package (opener-0597)

Run `npm run package:chrome` from `extensions/webextension` using Node.js 20 or newer.

This first executes the validated Chromium Manifest V3 build and creates
`dist/chrome/pdf-magic-opener-chrome-<version>.zip`, a Chrome Web Store
submission ZIP. It is not a signed CRX, published extension, or installation.

The ZIP root has exactly eight allowlisted files: `manifest.json`,
`background.js`, `popup.html`, `popup.css`, and four original local
`icons/icon-*.png` files. Firefox files, unbundled source modules, hidden
files, caches, private keys, symlinks and other files are excluded.

Archive records use ZIP STORE, CRC-32, a fixed DOS timestamp and stable order
for reproducible bytes. The builder rejects unexpected manifests, changed
assets and unsafe output directories. `dist/` and the ZIP are ignored by Git.

Packaging does not enable browser permissions, download monitoring, native
messaging, scanning or PDF opening. The popup remains inactive; the installed
native application independently enforces ClamAV freshness, file integrity,
quarantine, user-selected application preferences and safe handoff.

The required CI WebExtensions step runs `npm run package:chrome` and `npm test`
to verify the generated ZIP and its contents on every PR.
