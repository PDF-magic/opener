# Disable unreliable automatic PDF interception (opener-0799)

PDF Magic Opener must **not claim or activate automatic interception** merely
because a browser is installed, exposes a vendor API, or has a saved opt-in.
The current extension has no verified, authenticated browser-to-native
scan-before-render interlock. **Automatic interception is disabled in all nine
registered browser families until a separately reviewed implementation can
prove reliability.** The existing manual and explicit PDF scanning paths and
the user's preferred application remain unchanged.

The shared WebExtension's
[`assessAutomaticInterceptionReliability`](automatic-interception-capability-matrix.js)
and existing `assessAutomaticPdfInterception` surface explicit deny decisions:

| Browser or path | Reason to keep disabled |
| --- | --- |
| Chrome, Edge, Chromium, Brave, Vivaldi, Opera, Arc | Normal MV3 blocking cannot await a complete native scan; enterprise policy/conditional APIs alone do not prove an effective byte hold |
| Firefox main-frame network PDF | The response-filter API is documented, but no verified native scan, permission, timeout, and release interlock is installed |
| Safari | Safari-specific interception and permission behavior is unverified |
| Inline browser viewers, embeds, PDF.js, redirects, cached resources, blob/data/file URLs, attachments | Browser/version-specific capture and no-bypass protection cannot be guaranteed |
| Unknown browser or path | Unsupported/unverified by default |

The policy always returns an immutable disabled result with
`authorizesScan: false` and `authorizesOpen: false`, even when a synthetic
browser API object looks complete. The existing capability assessment also
exposes `automaticInterceptionDisabled: true` and a specific
`disabledReason`; it does not turn observed API shapes into scan/open
authorization. This is a *fail-closed activation gate*, not a universal
operating-system PDF open lock, a new browser listener, or a permission prompt.

Saved per-browser preferences remain untouched, including existing opt-ins.
Do not silently clear, overwrite, or reclassify user choices to represent
successful interception. A future implementation must prove the actual
installed browser/version and grants, all relevant paths, exact full PDF
bytes, trusted native ClamAV result, failure/revocation/restart handling,
and safe release under the user's chosen PDF-opening policy. That requires
a separate explicitly reviewed implementation and browser testing. This
task does not change the inactive background, manifest, UI, or scanner.

CI: `extensions/webextension/tests/automatic-interception-reliability.test.mjs`
runs automatically via the existing `npm test` WebExtensions suite. It
tests every browser, unsupported entry routes, fake API availability, strict
failure defaults, unchanged native permissions and user preferences.
