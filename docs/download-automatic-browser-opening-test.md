# Automatic browser PDF opening acceptance tests (opener-0722)

## Scope and interpretation

The automated Node regressions in
`extensions/webextension/tests/download-automatic-browser-opening.test.mjs`
exercise the existing passive download observer and managed native-opening
contract using a **simulated browser-owned auto-open action**. They demonstrate
that a browser's automatic opening can race ahead of download observation or a
pending scan, and that untrusted browser events cannot authorize an additional
PDF Magic native open. They **do not** prove that any installed browser can
intercept or postpone its own automatic open. The installed shared WebExtension
still has an inactive background and does not request `downloads.open`.

The earlier `download-managed-scan-before-open` regressions test clean-scan
correlation in isolation; this suite specifically exercises the **independent
automatic browser opening path** alongside that gate. No production preferences,
scanner behavior, interception permissions, or browser settings are changed.

## Real-browser acceptance procedure (not run by Node CI)

Only use a disposable, isolated browser profile and a harmless generated PDF.
Do **not** change a user's existing download, viewer, or default-app settings.
Use an isolated virtual machine if a test requires auto-launching a file. Keep
all scanner and quarantine protections active. Never use untrusted documents.

For each applicable installed browser and version:

1. Record the browser/version, macOS version, extension version and package,
   profile isolation, current PDF handling preferences, and whether the browser
   actually offers **automatic external opening after download**. Do not assume
   that an inline PDF viewer or a manual download-shelf open is auto-opening.
2. In the disposable profile, configure the browser's own automatic PDF-open
   preference only if explicitly supported. Initiate a benign PDF download.
   Record the completion event and whether the browser opens a tab or launches
   the system-associated application **before, during, or without** a native
   scan. Record the application receiving the PDF.
3. Repeat with browser inline-PDF viewing enabled and with automatic opening
   disabled. Distinguish these from a managed `Download, Scan & Open` request.
4. Test the same download while the extension is inactive, without its optional
   downloads permission, and when the native coordinator is unavailable.
   An automatic browser open is an **independent bypass**, not a verified scan.
5. After a separately authenticated native coordinator has actually been
   integrated, test pending, interrupted, failed, malware-detected, mismatched
   and completed clean results. The **managed native handoff** must never
   occur except after the native service independently revalidates the scan,
   file identity, quarantine and selected app. An unverified result is not
   sufficient even if the browser reports `state: "complete"` or `danger: "safe"`.
6. Restore/discard the disposable profile and record whether any test path
   escaped the managed workflow. Do not claim universal interception based on
   extension download-event visibility or a successful mocked test.

Cover Brave, Chrome, Chromium, Edge, Vivaldi, Opera, Arc, Firefox and Safari
where installed. Mark unsupported auto-open settings or unavailable extension
APIs **not testable**, never **passed**. For Safari in particular, do not assume
Chromium/Firefox download API parity. Capture the browser's built-in opening
behavior separately from native application handoff.

## Recording results

| Browser/version | Auto-open preference available? | Trigger and destination | Opened before verified native scan? | Managed handoff correctly blocked? | Evidence |
| --- | --- | --- | --- | --- | --- |
| *Not yet run* | *Unverified* | *None* | *Unverified* | *Unverified* | *Disposable-profile test required* |

**Production prerequisite:** The shared extension's background remains inert,
and the native messaging host is transport-only. An authenticated native
coordinator with real scan evidence and verified opening is not yet connected.
Consequently, CI can test only these contracts, not real end-to-end automatic
browser PDF opening or cross-browser interception. See
[controlled-opening support](download-opening-browser-support.md) for the
browser capability matrix and explicit limitations.
