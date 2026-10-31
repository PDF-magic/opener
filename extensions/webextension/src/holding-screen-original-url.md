# Preserve original URL in the holding screen (opener-0787)

A future extension-owned PDF holding screen can use the passive
`createHoldingScreenOriginalUrl(target, coordinator)` presenter with a
text element whose ID is `holdingScreenOriginalUrl`. The presenter initially
shows **Original PDF URL unavailable.**

A separately authenticated, permission-verified coordinator must capture the
**original browser navigation URL at interception time**, before redirects,
as ephemeral state. It exposes `trustedHoldingScreenReady`,
`readCurrentHoldingId()`, and promise-based
`readOriginalHoldingUrl({ holdingId })` returning exactly
`{ holdingId, originalUrl }`. The ready flag alone is not authentication.
`show(holdingId)` checks the currently held navigation before and after
the read, then displays the exact original HTTP(S) string as **textContent**,
including existing encoding, signed query and fragment. It never uses a
redirect's final URL or offers a URL-opening link.

This URL may contain secret tokens. Only display it to the affected user
within the extension-owned holding screen. Do not log, persist, sync, insert
in generic events, or send to native scanner messages. The presenter returns
no URL in its status record. Invalid/unsupported/credential-bearing URLs,
stale or mismatched holds, changed coordinators, and malformed replies fail
closed; `clear()` and `dispose()` erase the URL and invalidate pending reads.

**Integration:** opener-0785 now supplies the extension-owned holding
screen. That renderer creates the `holdingScreenOriginalUrl` text element only
after verifying a current scanning hold; this presenter then displays a
separately authenticated original navigation URL for that same hold.
The shared background remains inert. Actual interception and native scan
gating remain separate, and integration must preserve scanner safety and user
preferences.

Run `node --test tests/holding-screen-original-url.test.mjs` or `npm test`.
The existing WebExtension CI runs both the focused test and the full suite.
