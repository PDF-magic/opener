# Browser API compatibility layer (opener-0572)

`browser-compatibility.js` is a dependency-free, opt-in adapter for **runtime
metadata only**, shared by future Chromium, Firefox and Safari integrations.
Importing it is inert: it never reads browser globals, registers listeners,
requests browser permissions, monitors downloads, sends messages, opens files,
or initiates a PDF scan. It does not change the manifest or activate an
extension in any browser.

```js
import { createBrowserCompatibility } from "./browser-compatibility.js";

// Integration code must explicitly supply the host namespaces when needed.
const compat = createBrowserCompatibility({
  browser: globalThis.browser,
  chrome: globalThis.chrome
});
const manifest = compat.getManifest();
const iconURL = compat.getResourceURL("icons/icon-32.png");
const platform = await compat.getPlatformInfo(); // optional; may reject
```

Firefox generally exposes Promise-based `browser.runtime`; Chromium generally
exposes callback-based `chrome.runtime`. Safari WebExtensions may expose either
namespace. This adapter selects a *complete* `browser.runtime` first, otherwise
`chrome.runtime`, without user-agent sniffing or claiming to identify the
installed browser. The reported `namespace` is **not** an authentication,
scanner, or security verdict. It normalizes optional `getPlatformInfo()` to a
Promise, handles `chrome.runtime.lastError` inside the callback, and returns
generic errors rather than propagating potentially sensitive browser messages.
If an API is missing, it fails explicitly.

`getResourceURL` accepts bounded local asset paths only, rejecting absolute
paths, traversal, queries and remote URLs. No permission is requested.
This layer intentionally does **not** wrap message transport, download events,
content scripts, native messaging, file scanning or PDF handoff: those have
separate review and authorization requirements. No browser extension can
consider a PDF safe merely because a compatibility adapter exists.

The existing `npm test` script picks up `tests/browser-compatibility.test.mjs`;
the existing `scanner-tests` CI job runs it after the shared WebExtensions
build, without changes to the consolidated workflows.
