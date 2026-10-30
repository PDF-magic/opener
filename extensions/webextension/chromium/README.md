# Chromium compatibility smoke (opener-0601)

This validates the actual **unbranded Chromium browser**, separately from
Chrome Web Store ZIP packaging and Chrome for Testing (opener-0598) and
Brave-specific WebExtensions compatibility (opener-0599).

The new **Chromium MV3 extension smoke test** CI job installs a Chromium
snapshot, builds the already-validated unpacked extension in `dist/`,
and starts Chromium with a disposable profile. It requires a real Manifest
V3 service worker, successfully rendered popup, visible **Not active**
status, disabled **Scan PDF**, local CSS and no script errors.
Chromium's live browser API must report that optional `downloads`
permission is **not automatically granted**. Manifest tests require no
required API/host permissions, site content scripts, or incognito access.

To run manually, first build the extension and install the isolated
test-only driver:

```sh
npm run build
npm install --no-save --no-package-lock --ignore-scripts --no-audit --no-fund playwright-core@1.56.1
CHROMIUM_BINARY_PATH=/path/to/chromium node scripts/test-chromium.mjs
```

The existing `npm test` suite also discovers
`tests/chromium-compatibility.test.mjs` and verifies the exact built
assets and safety contract. The browser test **fails** if the extension
cannot load; static files alone cannot substitute for browser compatibility.
An enterprise-managed Chromium installation may prohibit loading unpacked
extensions, so CI fetches an unbranded Chromium snapshot instead. Branded
Google Chrome 137+ removed the corresponding unpacked-extension flags;
that browser is covered by its separate task, not by pretending it is Chromium.
The Playwright automation driver is installed for CI only and is never
included as a runtime dependency.

The smoke test never visits external websites, loads PDF documents,
requests grants, contacts the native scanner or selects applications.
Its temporary browser profile is discarded even when the test fails.
The existing ClamAV freshness, quarantine, file integrity, verified
opening and user's selected PDF destination remain fully authoritative.
