# Fail-closed permission revocation handling (opener-0590)

`permission-revocations.js` exports `normalizePermissionRevocation(details)` and
`subscribeToPermissionRevocations(permissionsApi, onRevoked, { onError })`.
The observer subscribes only after a separately reviewed browser integration
explicitly calls it with a trusted WebExtensions `permissions` namespace.
Today's shared background entry point remains inert, and the current manifest
requests no install-time privileges or site access. There are **no automatic
permission requests or re-grants**.

The subscription uses `permissions.onRemoved.addListener/removeListener`. When
a relevant revocation arrives, it **synchronously latches** the affected flags
before invoking the caller's cleanup callback:

- `downloadsRevoked`: stop download event subscriptions and cancel work relying
  on download permission.
- `nativeMessagingRevoked`: terminate separately reviewed native messaging
  sessions and cancel pending messages, without bypassing the native scanner.
- `notificationsRevoked` and `storageRevoked`: stop operations requiring those
  browser API grants; never erase stored user preferences or assume a new grant.
- `siteAccessRevoked`: disable site-dependent work on any origin revocation.
  Individual site origin strings are deliberately excluded from notifications.

Unknown valid API permissions do not affect unrelated capabilities. Invalid
or accessor-bearing permission-removal payloads conservatively revoke all
tracked capabilities. Duplicate removals are idempotent, and `unsubscribe()`
detaches the listener. Cleanup errors are isolated; an `onError` callback
receives a fixed message rather than a potentially sensitive native path.

```js
import { subscribeToPermissionRevocations } from "./permission-revocations.js";
import { subscribeToDownloadEvents } from "./download-monitoring.js";

// Illustrative future, explicitly authorized integration, not active today.
const stopDownloads = subscribeToDownloadEvents(trustedDownloads, handleDownload);
const revocations = subscribeToPermissionRevocations(trustedPermissions, (state) => {
  if (state.downloadsRevoked) stopDownloads();
  if (state.nativeMessagingRevoked) stopNativeMessagingAndCancelPendingRequests();
  if (state.siteAccessRevoked) stopSiteDependentOperations();
});
// On teardown: revocations.unsubscribe().
```

**Security boundary:** a `false` revocation flag means only that this watcher
has not observed the corresponding removal. It is *not* evidence the browser
ever granted that permission; `permissionsVerified` and `authorizesOpen` are
always `false`. The caller must check current effective grants before *every*
privileged operation, and must cancel in-flight work on revocation. An
`onAdded` event never clears these latched restrictions; reauthorization needs
a new trusted and explicitly consented integration. A newly installed extension
worker must revalidate effective grants before attaching operations.

No changes are made to user-selected PDF applications, native ClamAV signature
freshness/integrity/quarantine checks, scan acceptance, or opening decisions.
The required `scanner-tests` CI runs the extension's Node test wildcard,
including `tests/permission-revocations.test.mjs` and its real download-event
teardown integration test.
