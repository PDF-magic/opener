# Arc for macOS compatibility test (opener-0604)

This checks the **actual Arc for macOS browser** separately from the Chrome,
Chromium, Brave, Edge, Vivaldi and Opera compatibility tasks.

The dedicated **Arc macOS MV3 extension smoke test** GitHub Actions job
installs the official Arc application through Homebrew's `arc` cask and
verifies the installed macOS app bundle identifier
`company.thebrowser.Browser` and its code signature. It builds the existing,
validated unpacked `dist/` Manifest V3 extension, then launches the actual
Arc executable with an isolated disposable browser profile and a
loopback-only Chrome DevTools Protocol endpoint, which is Arc's supported
automation interface. The smoke test
**must observe the real registered extension service worker** and
browser-rendered popup, including local styling and the disabled **Scan PDF**
control. It checks Arc's effective extension manifest and that the optional
`downloads` permission has not silently been granted.

Arc may require user sign-in or restrict extensions in unattended/headless
sessions. In that case **the real-browser CI check fails closed** rather
than claiming compatibility from generic Chromium tests or faking a loaded
extension. Arc's manual `arc://extensions` interface may allow loading
an unpacked extension in Developer Mode, but manual installation alone
does not substitute for the automated browser check.

## Manual test on a Mac

Build the extension with `npm run build`, install the Arc app from its
official distribution, and install a test-only automation driver:

```sh
npm install --no-save --no-package-lock --ignore-scripts --no-audit --no-fund playwright-core@1.56.1
ARC_APP_PATH=/Applications/Arc.app node scripts/test-arc.mjs
```

Or manually open `arc://extensions`, enable Developer Mode and load the
unpacked `extensions/webextension/dist/` directory into a disposable
Arc profile. Verify the toolbar opens the **Not active** popup and that
**Scan PDF** remains disabled. Do not click the external preferences link
or load real or sensitive PDFs during a compatibility check.

The normal shared WebExtensions `npm test` suite also runs
`tests/arc-compatibility.test.mjs` to guard the source/build metadata and
inert assets. No production dependencies, extension permissions, native
messaging, page access, scanner safety checks or user preferences change.
Arc is a third-party browser with an independent support lifecycle.
If its signed distribution or unattended extension loading becomes unavailable,
report that failure as a compatibility limitation rather than bypassing CI.
