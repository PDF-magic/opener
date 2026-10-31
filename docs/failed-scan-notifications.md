# Failed-scan notifications (opener-0890)

The installed native PDF handler distinguishes verified operational scan failures
and incomplete scans from other blocked-opening outcomes when **Show Blocked
File Notifications** is explicitly enabled. It reuses that existing opt-in,
which remains disabled by default. A verified failure produces a single
privacy-safe notification: **“A PDF scan failed or could not finish. The file
was not opened.”** There is no second notification for the same request.

Only exact, fixed diagnostics from the trusted single-file native scanner gate
qualify: scanner errors, timeouts, incomplete checks, missing signatures and
scanner initialization failures. Confirmed malware, suspicious content, unknown
diagnostics, arbitrary errors, post-scan handoff failures and cancellations are
not mislabeled as scan failures. Other eligible failures retain the ordinary
blocked-file notice. No filenames, paths, raw scanner logs or PDF content are
interpolated into notification text.

The mandatory native error alert remains independent of optional notifications.
macOS permission denial is respected, and delivery is best effort; it never
changes opening, scanner enforcement, quarantine or saved customizations.
The separate browser-download **Notify on Failed Scan** setting is not
activated because its authenticated native download coordinator is not yet
connected.

Linux and macOS CI validate the exact-result classifier, opt-in, cancellation,
path-free delivery, mandatory alert retention and isolated preference behavior.

Confirmed malware retains the dedicated notification introduced in merged
PR #612 and takes priority over the operational failed-scan message. Both
categories reuse one opt-in notification dispatch, not duplicate alerts.
