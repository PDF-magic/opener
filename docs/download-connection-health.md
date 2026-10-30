# Browser-to-native connection health (opener-0734)

The **Browsers → Connection health** group displays a global, accessible,
read-only connection-health indicator. Its current status is **Not connected**
because the browser extension is inactive and no authenticated, live,
browser-to-native connection observer is installed.

This is **not** the per-browser monitoring-status list (opener-0733).
An installed browser, saved monitoring opt-in, locally registered host or
host-transport handshake is never evidence of an operational scanner session.
The existing native host advertises `status: transport-only` with
`scanAvailable: false`; its handshake cannot verify browser-download
scanning. Showing a green Connected indicator would therefore be inaccurate.

The pure `BrowserNativeConnectionHealth` presentation contract has only
**notConnected** and **transportOnly** states. A future authenticated
coordinator may derive **Host reachable — scanning unavailable** only when
registration, exact approved browser identity, live session and handshake
are independently verified, with protocol v1, `transport-only` status and
`scanAvailable: false`. Unsupported or privileged replies remain
**Not connected**. No scanner-healthy state can be manufactured in this
task. A future live status source requires separate security-reviewed work;
this indicator does not probe the browser, open a native connection, read
downloads or infer health from preferences.

No user choice is read or changed for connection-health display. It does
not add a permission, start scanning, alter failure warnings or fail-closed
opening, interfere with installed native ClamAV, or change the chosen PDF
application. Existing download settings remain independently functional.

CI runs `tests/general/download-connection-health.py` for UI and inactive
transport boundaries, and compiles/runs
`test-download-connection-health.swift` to cover truthful initial status,
host-transport-only state, invalid and privileged claims, and preservation
of unrelated settings in a disposable preferences suite.
