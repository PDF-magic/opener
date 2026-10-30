# Shared extension initialization error handling (opener-0580)

`src/initialization-errors.js` provides a passive, dependency-free
`createExtensionInitializer(steps)` lifecycle for future browser integrations.
**Nothing starts when the module is imported.** The existing inert background
worker and permission-free extension manifest remain unchanged.

Supply an ordered list of trusted initialization functions and explicitly call
`start()`. Each step must return (or resolve to) a cleanup function.
After successful setup, `state()` reports `initialized`, meaning only that
the supplied setup functions completed; it **does not mean** a scanner is
connected, a document has been verified, or PDF opening is allowed.

On initialization failure, previously acquired resources are disposed in
reverse order. If cleanup fails, later disposers are still attempted. Error
messages, paths, URLs, raw exceptions and browser data are never returned or
logged. Callers receive immutable states and fixed error codes:

- `INITIALIZATION_UNAVAILABLE` for an absent integration.
- `INITIALIZATION_FAILED` for failed startup with successful rollback.
- `INITIALIZATION_CLEANUP_FAILED` when rollback or shutdown fails.

Concurrent `start()` calls share the same operation, and an explicit
`stop()` during startup cancels later steps, finishes the current step and
rolls back acquired resources. A stopped or failed controller does not
implicitly retry; reconstruct one only after the failure is addressed.
A step that fails **after partially acquiring resources** must clean up its
own partial work before throwing, because it has not returned a disposer yet.

This module does not read or update stored user preferences, request browser
permissions, start download monitoring, use native messaging, scan PDF bytes,
or grant authorization to open anything. Future initialization wiring is
separate and must honor existing ClamAV, signature freshness, quarantine and
verified application handoff requirements. Initialization errors cannot be
misrepresented as clean scan results.

The existing WebExtensions CI runs `npm test`; it automatically discovers
`tests/initialization-errors.test.mjs` and verifies ordered teardown,
concurrency, cancellation, fixed errors, and the absence of import-time side
effects.
