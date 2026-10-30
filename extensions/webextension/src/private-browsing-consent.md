# Explicit private-browsing consent (opener-0594, section 9.2)

The current shared WebExtensions scaffold does **not** activate private or
incognito download monitoring, native messaging, PDF scanning, or PDF opening.
PR #386 (opener-0593) separately adds an incognito mode of **not_allowed**
to the Chromium, Firefox and Safari shared manifests. This consent module
does **not** change or override that prohibition. A browser-specific private
integration would require its own privacy review, browser-specific tests,
and an approved manifest change where supported.

## Per-session requirements

The dependency-free source module src/private-browsing-consent.js exports
createPrivateBrowsingConsentGate(extensionApi, verifyPrivateSession) and a
fixed user-facing consent notice. A gate starts with **no consent** and
never performs browser work on import or construction.

1. Construct a **fresh gate for each verified private session**. Inject
   the explicitly selected browser's extension namespace, supplying its
   isAllowedIncognitoAccess() method where supported. Inject a trusted,
   session-bound verifyPrivateSession() callback that resolves to true only
   while that same private session is active. Neither a download URL nor a
   stored preference can establish private-session identity.
2. Present a separate, optional, clear private-session consent choice to
   the user. Call recordConsent({ userInitiated: true }) only from the actual
   affirmative user-action handler. That boolean is a caller assertion and
   not evidence of a browser-trusted user gesture. Browser access alone is
   not application consent.
3. Require await canProcessPrivateData() === true **before every private
   operation**. The gate rechecks effective browser incognito permission
   and the original private session on each call. A positive consent state
   is not permission to scan or open PDFs: native host authorization and
   all existing scanner policy checks are independent prerequisites.
4. Call endSession() on private session termination, explicit consent
   withdrawal, or feature disablement. The gate cannot be reused and any
   new session needs a fresh opt-in.

Denied access, an unsupported or callback-only API, unknown context,
invalid or failed checks, and revoked permission **all fail closed**.
A later browser grant cannot revive the invalidated gate. Concurrent
opt-in attempts share one check and a late response cannot reactivate an
ended session. No consent, browsing identifiers, file paths or document
metadata are stored, logged, transmitted or persisted.

## Browser and integration boundaries

Chromium and Firefox must continue honoring the separately reviewed
not_allowed manifest policy; this helper does not weaken it. Safari also
has independent, user-managed private-browsing controls and may interpret
manifest restrictions differently across versions. Future integrations
must verify browser support, securely bind the private session checker,
and enforce this separate consent gate before activating any access.
Unsupported integrations remain disabled. This task deliberately does not
wire an active private-browsing feature or request any extra permissions.

This policy does not affect the installed scanner's ClamAV freshness,
document integrity, quarantine or verified application handoff gates.
User-customized settings remain untouched.

The existing WebExtensions npm test step automatically runs
tests/private-browsing-consent.test.mjs. Tests cover missing consent,
browser-level refusal, unsupported APIs, malformed accessors, separated
sessions, revocation, cancellation races and import-time inactivity.
