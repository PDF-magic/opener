# Automatic PDF interception holding screen (opener-0785)

**Status: defined, inactive.** The shared browser extension still has an inert
background and no automatic PDF interception or native scan interlock.
This change defines the holding screen for a future opt-in implementation,
without enabling interception or changing any scan policy or user preference.

## What the screen displays

The passive renderer in [pdf-interception-holding-screen.js](pdf-interception-holding-screen.js)
creates a responsive, accessible screen using only extension-owned DOM
elements and fixed text:

- **Scanning PDF before opening**
- **Opening is paused while PDF Magic Opener checks this PDF.**
- **This PDF is not yet verified as safe. Opening remains blocked.**

The separate [CSS](pdf-interception-holding-screen.css) provides light and
dark appearance, readable large text, a decorative activity indicator, and
reduced-motion support. The root has role=status, polite live status,
aria-busy=true and a label referring to the screen heading. There is no
skip-scan, open-original, accept-risk, download or retry control. URLs,
PDF content, filenames, local paths and native scanner errors are never shown.

## Activation contract

The screen starts hidden and empty. A later trusted integration must create
an **extension-owned** root with id pdfInterceptionHoldingScreen and load the
CSS in its own origin. The caller must independently verify an effective
pre-render navigation hold, current PDF identity, an explicitly opted-in
supported browser, valid permissions, and an authenticated, started native
scan before invoking show.

show(context) requires exactly navigationId and scanRequestId, bounded
opaque ASCII identifiers. Its separately authenticated coordinator must
expose verifiedPdfInterceptionReady=true and a synchronous function named
readVerifiedHeldPdfScan(context), returning exactly the matching IDs,
state=scanning, navigationHeld=true, nativeScanStarted=true and
authorizesOpen=false. The returned record or readiness flag by itself
**does not authenticate** the browser or native scanner. Missing, malformed,
mismatched, stale or unsafe inputs fail closed and leave the screen hidden.

A visible screen is not a clean scan verdict and never authorizes a scan or
opening: both return values remain false. The integrating controller MUST
clear the screen on completion, failure, cancellation, permission revocation,
timeout or navigation change. The renderer never polls, registers listeners,
starts a scan or opens any PDF. A browser without an enforceable pre-render
hold must not use this screen as proof it stopped rendering.

**Missing prerequisites:** reviewed real automatic interception for a
supported browser, an enforceable navigation veto, safe byte capture,
native-scan request correlation, and an authenticated scan interlock.
See [preload interception](pdf-preload-interception-trigger.md) and
[capability matrix](automatic-interception-capability-matrix.md).
Those are separate tasks; no manifest, background, scanner or user preferences
are modified here.

Dedicated tests cover accessibility, lifecycle, privacy, fail-closed
conditions and unchanged scanner and browser-privilege boundaries.
The existing WebExtensions npm test glob and explicit CI step run them.
