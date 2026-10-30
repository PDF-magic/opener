# Extension update handling (opener-0581)

The shared WebExtensions module `src/extension-updates.js` exposes
`normalizeExtensionUpdate(details, currentVersion)` and
`subscribeToExtensionUpdates(runtime, onUpdate, { onError })`.

The subscription must be **explicitly initialized** by a future, separately
reviewed browser background integration. The existing packaged background script
remains inert. No listener is registered at module import time.

Callers provide a standard WebExtensions `runtime` object with
`onInstalled.addListener/removeListener` and `getManifest()`. The callback
receives only an immutable, minimal
`{ kind: "extension-update", previousVersion, currentVersion }` record,
and **only** after a genuine `reason: "update"` event with well-formed,
different extension versions. Installation, browser update, module update and
malformed events are ignored. Repeated notifications for the same version
transition are deduplicated while subscribed.

```js
import { subscribeToExtensionUpdates } from "./extension-updates.js";

// Only from a later reviewed integration, never automatically from this module:
const unsubscribe = subscribeToExtensionUpdates(trustedRuntime, (event) => {
  // Read-only awareness. Migration and user-facing notification are separate tasks.
  reportSafeUpdateMetadata(event);
});
// Later, unsubscribe() releases the registration.
```

**Fail-closed boundary:** This module never migrates, resets, overwrites or
removes stored preferences, removes cache entries, triggers a browser reload,
downloads anything, requests permissions, contacts the native app, scans a PDF
or opens a document. It does not infer PDF protection from an extension update.
The installed app's fresh signature checks, malware scanning, quarantine and
user-chosen PDF destination remain the only authoritative opening gate. Any
future configuration migration needs an independent, reviewed and tested
versioned contract; an update event alone is not consent to change settings.

The existing `npm test` wildcard runs
`tests/extension-updates.test.mjs` in the required WebExtensions CI suite.
