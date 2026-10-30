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

## Run the actual package in Chrome (opener-0598)

The `Chrome package smoke test` CI job builds the **same Web Store upload ZIP**
using `npm run package:chrome`, extracts it into a temporary directory and
loads that **extracted archive**, not the source tree, as an unpacked extension
in **Chrome for Testing (stable)**. This is a real headless Chrome process
using the modern headless mode and Chrome DevTools Protocol, with an isolated
disposable profile and no added npm dependencies.

The smoke test requires Chrome to register the Manifest V3 service worker and
render the packaged popup from a `chrome-extension://` URL. It verifies the
actual browser-reported extension name, private-browsing restriction, absence
of required host/API permissions, ungranted optional-download declaration,
disabled Scan PDF control, **Not active** warning, static styling and
user-initiated native-preferences link. It never clicks the external-app link,
visits websites, grants permissions, scans documents or changes user settings.

Chrome 137+ branded builds do not support command-line `--load-extension`.
The CI job installs Google's **Chrome for Testing** distribution through
`browser-actions/setup-chrome@v2`, which supports this documented testing
workflow. A missing browser, rejected extension, missing worker or broken
popup fails CI rather than being reported as a pass. For a local run, install
Chrome for Testing, then run:

```sh
npm run package:chrome
mkdir -p /tmp/pdfmagic-chrome-smoke
unzip -q "dist/chrome/pdf-magic-opener-chrome-$(node -p 'require("./manifest.json").version').zip" -d /tmp/pdfmagic-chrome-smoke
node scripts/test-chrome.mjs /path/to/chrome-for-testing /tmp/pdfmagic-chrome-smoke
```

This tests browser loading and the intentionally inactive extension **only**.
It is not Chrome Web Store publication, signing, end-user installation,
native scanner verification or PDF opening approval. Those need separate
review and testing.

For Linux CI environments where an unprivileged Chrome sandbox cannot start,
the disposable test browser alone uses `CHROME_TEST_NO_SANDBOX=1`. This does
not alter the packaged extension, production browser behavior, native ClamAV
sandboxing or application preferences; Chrome still loads **only** the extracted
local ZIP in an isolated profile.
