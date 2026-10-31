# Sanitizer-failure notifications (opener-0891)

An optional **Maximum** sanitization failure is distinct from malware detection,
scanner failure, or a verified clean result. A trusted future Maximum caller
can report the existing five-field `SanitizerFailureReport.to_dict()` JSON
through `ScanProgressPanel.updateMaximumSanitizationFailure(from:)`.
Only a validated canonical `sanitizerFailure` report with its exact kind and
fixed message, `scanVerdict=notAssessed`, and `permitsOpen=false` is
eligible for a system notification. Malformed, oversized, path-bearing,
unknown, or forged reports retain the safe blocking UI but do not notify.

The native PDF owner installs a callback for that validated event. It reuses
**Show Blocked File Notifications** (off by default) and the existing macOS
notification permission flow, rather than adding an unexpected opt-in or
changing a user's settings. A validated failure can publish the single fixed
message: **“PDF sanitization failed. No sanitized copy was produced. This
is not a malware detection.”** No PDF name, path, content, scanner output,
or subprocess details enter the notification. Repeated updates for one
failure send no duplicate; a fresh request resets the notification guard.
Notification denial or failure never affects scan or opening decisions.

**Deployment boundary:** The installed Built-in ClamAV gate does not run
the optional Maximum sanitizer; the Maximum profile remains nonselectable.
These notifications are ready for the existing trusted native sanitizer
failure presentation hook, but cannot fire during ordinary Built-in scans
until a separately scoped Maximum coordinator invokes that hook. This
change does not activate sanitization or add any bypass, output acceptance,
quarantine removal, scan verdict, or preference migration.

Required Linux CI verifies the classification, privacy and delivery wiring.
Existing macOS scan-progress rendering tests exercise valid, duplicate,
forged and reset callbacks; its native build compiles the notification owner.
