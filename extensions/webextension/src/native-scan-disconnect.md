# Extension disconnection during native scanning (opener-0636)

The browser extension does not yet have an authenticated native scan coordinator.
The standalone Swift native host rejects scan requests and cannot initiate a
scan, so connecting a real scanner or requesting native messaging permission
here would bypass an unfinished security boundary.

The opt-in, side-effect-free native-scan-disconnect.js module is for the future
trusted extension-to-native integration. A trusted coordinator must explicitly
pass its native messaging Port to createNativeScanDisconnectGuard(port) and
track each already-accepted scan with an opaque token and its own cleanup
callback. Neither a transport connection nor a tracked token authenticates the
extension or authorizes reading, scanning, or opening a PDF.

On Port.onDisconnect or explicit disposal, the guard synchronously latches
the connection as lost, revokes all outstanding tokens, and invokes each
registered cleanup callback exactly once. The trusted coordinator must use
these callbacks to cancel and reap only its own active scanner jobs. Cleanup
failures cannot reinstate tokens or skip other callbacks. Late asynchronous
results from the disconnected session must be discarded by checking
isActive(token) immediately before consuming a result; release(token) removes
successfully completed jobs from disconnect cleanup. A new native Port requires
a new guard and cannot reuse tokens from an old connection.

The guard itself never launches or kills a process, registers a native host,
requests permissions, reads files, reports a verdict, changes saved preferences
or invokes PDF opening. The future integration must still authenticate browser
identity, obtain trusted local PDF selection, enforce existing ClamAV signature
freshness, complete scanner evidence, integrity and quarantine checks, and
perform the separately verified PDF-opening handoff. It must also ensure
disconnect callbacks abort any running job rather than merely hiding UI state.

Regression tests under tests/native-scan-disconnect.test.mjs exercise live
disconnects, reentrancy, late results, reconnect isolation, idempotent cleanup,
error containment and preservation of the inactive extension. The established
WebExtensions npm test suite includes this test automatically.
