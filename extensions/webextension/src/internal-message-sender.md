# Extension-internal message sender verification (opener-0662)

`internal-message-sender.js` defines a dormant, fail-closed check for future
`runtime.onMessage` listeners. There are **no listeners** in the packaged
background today; merely importing the helper never enables message handling,
scanner access, extension permissions, or preference writes.

A future reviewed listener must call
`isVerifiedInternalMessageSender(sender, browser.runtime)` (or the genuine
`chrome.runtime` API) with the **browser-supplied `MessageSender` argument**, and
reject the message before decoding, dispatching, or acting on its payload if
verification returns `false`. Never pass `message.sender`, a payload-provided
extension ID, or a caller-constructed runtime object as authority.

Admission requires the exact browser runtime ID, a browser-controlled sender
URL within the same extension scheme and host as `runtime.getURL("/")`, and no
`sender.tab` indicating a page content script. If `sender.origin` is provided,
it must agree with the trusted extension URL. Missing values, hostile getters,
wrong browser schemes, unknown origins, external extensions, and webpages fail
closed. Firefox's random `moz-extension://` host is deliberately compared to
`runtime.getURL("/")`, not incorrectly to its Gecko add-on ID.

This is a boundary for **extension-internal pages only**; it is not native host
caller authentication and does not authorize scanning or opening files.
Application scan policy, ClamAV freshness, integrity, quarantine, and explicit
user selection remain separately enforced. A future feature that intentionally
accepts content-script messages must receive a separate, reviewed policy.

Regression tests: `node --test tests/internal-message-sender.test.mjs` from
`extensions/webextension`. The existing required `scanner-tests` job executes
these tests through `npm test` after both browser builds.
