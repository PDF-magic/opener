# Handle browser closure during native scanning (opener-0707)

createBrowserScanClosureGuard(port, lifecycle) is a passive, opt-in adapter
around the already merged createNativeScanDisconnectGuard. The caller
must independently authenticate the native scanner coordinator and obtain
explicit user consent. It must track only already accepted native scan jobs
with cleanup callbacks that cancel and reap those coordinator-owned jobs.

On browser service-worker suspension the optional injected privileged
runtime.onSuspend source synchronously invalidates every tracked token and
invokes all pending cancellation callbacks. Port.onDisconnect independently
provides the fallback when the browser closes without onSuspend or the
browser does not support that event. Worker suspension can also happen
without browser closure; cancelling outstanding work is intentionally
fail-closed. Releasing a completed token prevents unnecessary cancellation.
Disposal is idempotent and removes the optional suspension listener.

Hard shutdown limitation: browser processes can die without delivering
JavaScript callbacks or allowing a native Port.onDisconnect handler to run.
The trusted native job owner MUST separately monitor native pipe EOF,
browser process death, and orphaned children, cancel and reap its own scan
process groups, and never open a PDF based on a late result. The standalone
Swift native host already exits on pipe EOF but remains transport-only,
rejects scans, and has no child scanner jobs. This module does not create
the missing native scanner coordinator or promise hard-kill cleanup.

The frozen object exposes track(cancelScan), isActive(token), release(token),
connectionLost(), and dispose(). Tokens are local opaque symbols and never
browser-originated scan IDs, paths or process IDs. The integration must
check isActive(token) immediately before consuming any async result.

No scanner is invoked, no browser runtime is accessed on import, and no
native host is registered or connected. Existing ClamAV freshness, whole
file scanning, integrity, quarantine, selected application, permissions
and user customizations stay unchanged. The installed extension background
remains inactive.

The eleven focused Node regression tests are included in WebExtensions
npm test and required scanner-tests GitHub CI.
