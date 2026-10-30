# Scan This PDF extension result display (opener-0773)

The shared extension's toolbar popup includes an accessible **Scan result**
section. Its default message is **No verified scan result is available.**
Because the shipped background remains inactive and its native messaging host
is transport-only, this is the only state shown by the installed popup today.

The passive `createExplicitPdfScanResultDisplay(target, coordinator)`
renderer can populate the extension-owned result paragraph after a future
trusted integration authenticates a native scanner and correlates its
request to the selected PDF. The caller must supply exact bounded opaque
requestId, scanRequestId and selectionId values. The renderer rechecks the
coordinator's readiness, callbacks and current PDF selection after awaiting
`readVerifiedExplicitPdfScanResult`. A version-1 scan.result response
envelope must match both request IDs and have a strict payload.

A verified, completed clean result is shown as a polite live status that
**does not authorize opening**. A verified malware result is an assertive
blocking alert. Recognized blocked or failed statuses show a generic
assertive **Do not open** warning. Missing, unavailable, mismatched,
incomplete, malformed or stale results reset the view to neutral, clearing
any previous clean text. Clear/dispose invalidates outstanding async work.

Only fixed status messages are assigned through textContent. No filenames,
paths, URLs, scanner signatures, native errors or HTML are rendered. The
input records' fields or a readiness boolean do not alone authenticate
scanner evidence. The future trusted coordinator must independently bind
user action to the exact PDF, enforce scanner signature freshness, full
scanning, stable file identity, quarantine and separate open authorization.

**Activation prerequisite:** the popup validator intentionally forbids
script tags, and the extension background is inert. This feature adds the
visible neutral result area and reusable renderer but does not activate a
live native-to-popup data path. A separately authorized integration must
attach it before the extension can show live verdicts. The existing
disabled toolbar controls, extension permissions, scanner safety, and
saved user preferences are unchanged.

Dedicated tests verify popup accessibility/asset validation, static
defaults, trusted clean and blocked presentations, fake replies,
selection races, stale-state invalidation, privacy and unchanged
extension privileges. The suite runs under npm test and explicit CI.
