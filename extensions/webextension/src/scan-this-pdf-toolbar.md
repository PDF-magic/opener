# Scan This PDF toolbar action (opener-0756)

The installed WebExtensions toolbar popup displays a separate **Scan This PDF**
control in its **Current PDF** section. It is distinct from the existing
**Scan PDF** manual action, which remains unchanged, as do user preferences.

This action is **visible but permanently disabled**, with a separate,
screen-reader-linked explanation. The browser integration does not have a
verified native scanner and a trusted way to select the *currently displayed*
PDF. A URL path, page-provided PDF claim, or browser tab title does not
authorize native scanning, fetching, file opening, or access to page contents.
The existing `src/background.js` remains inert. The manifest grants no new
permissions, and the UI does not register handlers, load scripts or contact a
native host.

A subsequent, separately reviewed integration must authenticate the browser
tab/document context, safely resolve the intended current PDF to a local file,
obtain any required permissions and user consent, submit it to a trusted native
scan coordinator, and preserve all existing ClamAV signature freshness,
integrity, quarantine, verified scan-before-open and user application settings.
Simply enabling this HTML control is never a safe substitute for that work.

`scripts/popup-assets.mjs` strictly validates the exact disabled markup and
its explanation, rejecting any enabled, missing, duplicated, renamed or
scripted scan control. `tests/popup.test.mjs` covers accessibility,
injection rejection, and packaging of the popup in both Chrome and Firefox.
The existing `npm test` and GitHub CI execute those tests without adding a
new workflow or changing scanner behavior.
