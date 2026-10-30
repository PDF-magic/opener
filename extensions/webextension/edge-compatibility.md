# Microsoft Edge compatibility smoke test (opener-0600, §9.3)

Microsoft Edge is Chromium-based, so it uses the existing **validated
Chromium Manifest V3 output** in `dist/`. This task does not create a
separate extension identity, broaden permissions or activate PDF handling.

Run the shared source/packaging test with:

```sh
cd extensions/webextension
npm run build
node --test tests/edge-compatibility.test.mjs
```

CI also uses the **real Microsoft Edge and matching EdgeDriver** installed
on GitHub's `windows-2022` runner, with Node.js 22 and no new npm packages.
It opens the built `popup.html` in a temporary, isolated Edge headless
profile and verifies the loaded styles, truthful inactive status, disabled
Scan PDF control, visible explanation and existing preferences link.

The portable test compares all eight local Chromium assets byte-for-byte
with their validated sources, and checks the MV3 worker, action metadata,
required/optional/host permissions and private-browsing exclusion. There
are no scripts in the popup and the worker stays inert.

**Test scope:** This is a real-Edge **rendering and packaged-source
compatibility smoke test**, not a Microsoft Edge Add-ons store installation
or a live extension/worker activation test. Modern branded Edge releases
restrict unpacked extension side-loading through browser command-line
flags. A later signed/add-ons submission and manual installation review
must confirm extension lifecycle behavior on supported Edge versions.

The headless test disables other extensions, uses only a local file URL
and loopback WebDriver, performs no downloads or external network requests,
does not invoke the preferences link or enable native messaging, and
removes its temporary profile. Absence of EdgeDriver is a test failure in
Windows CI (the test is skipped in the normal dependency-free Node suite).
No installed PDF handler, ClamAV gate, quarantine rules or user choices
are changed.
