# Desktop application closure during a download scan (opener-0708)

`createDownloadDesktopClosureGuard(coordinator)` is a passive, opt-in
download-scan session guard for a **separately authenticated native desktop
application lifecycle**. It is intended to handle the desktop scan owner
closing while completed downloads are still being scanned, even if the
browser-to-native Port has not yet disconnected.

## Native integration contract and prerequisite

The trusted coordinator must independently authenticate its desktop
application and provide own-data `nativeDesktopLifecycleReady: true` and
`onDesktopApplicationClosed: { addListener, removeListener }`. It must emit
the closure signal when the **actual native owner** terminates or becomes
unavailable. Neither a flag nor an event object authenticates a process.
Never source this signal from browser page events, download metadata or
untrusted JavaScript messages.

When a download scan is **already accepted by the native scanner**, the
trusted integration may call `guard.track(cancelScan)` with its native-owned
cancellation callback. On application closure, all tracked tokens are
atomically revoked **before** cancellation callbacks are invoked.
Callbacks run synchronously in registration order so the owner can stop
ClamAV and the native child process promptly. Failures in one callback
cannot skip others, and rejected cleanup promises are contained. Further
registrations are refused. `guard.isActive(token)` and
`guard.release(token)` let the owner check and retire accepted work.
`guard.receive(token, promise)` suppresses late results after closure,
explicit disposal, or token removal, returning a frozen, non-authorizing
`{ status: "unavailable", scanVerified: false, authorizesOpen: false }`
object rather than a stale clean/open-capable result. A live result remains
**unverified input**: this adapter does not certify scan evidence, and
independent native verification and opening gates still apply.

The existing native PDF handler already cancels ClamAV when its owner
terminates: see merged PR #31 (opener-0060), the
`PDF_MAGIC_PARENT_LIFETIME` stdin pipe, `watch_parent_lifetime()` in
`scan-and-open.py`, and `test-app-termination.py`. The existing
`native-scan-disconnect.js` handles browser Port loss, which is **not**
a substitute for desktop application closure. This PR does not duplicate
those cancellation mechanisms.

The standalone SwiftUI preferences application is currently not the owner
of running PDF scans, and the present native messaging host is still
transport-only. A future authenticated downloaded-PDF scan coordinator
must establish real app ownership, emit the closure event and make the
cancellation callback terminate the owned native scan. Until then,
this module does not claim that an active production download scan can
run or be stopped through the browser extension.

## Security and test coverage

No native messaging, scanner invocation, browser download listener, tab
event, polling, file access, or permission request occurs on import. The
module does not alter ClamAV limits, verified scan results, file integrity,
quarantine, PDF opening, or user preferences. The desktop closure latch
does not automatically resume scans when an app is restarted; new scans
require a new authenticated native session.

The 13 Node regression tests in
`tests/download-desktop-closure.test.mjs` run under the existing
WebExtensions `npm test` / mandatory `scanner-tests` CI. They cover
closing during a pending scan, cancellation isolation, late clean-result
rejection, owner shutdown, event registration races, cleanup failures,
missing or untrusted lifecycle providers, and inert browser behavior.
