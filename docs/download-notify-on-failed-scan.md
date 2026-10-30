# Notify on Failed Scan download setting (opener-0732)

The **Browsers → Download failure notifications** section provides an accessible
**Notify on Failed Scan** toggle. Its initial value is **off**: there are no
unrequested browser-download notifications. Switching it on persists the
explicit `notifyOnFailedScan` Boolean inside the existing preferences suite.
Missing, malformed and unavailable settings are treated as off without writing
over a stored value during page load. An explicit save validates the persisted
Boolean and restores a prior choice on failure.

`DownloadFailedScanNotificationPreference.shouldNotify` only considers a
**verified failed or incomplete native download scan** eligible for an
*additional* notification, and only after explicit user opt-in. Clean scans,
malware/blocked-file outcomes managed by existing safety warnings, cancellation,
and unknown or unverified results do **not** qualify for this separate optional
notification. Existing blocking decisions, mandatory failure messages and
security warning presentation are never controlled by this option.

**Prerequisite:** Browser-download monitoring and a trustworthy native
scan-report/notification coordinator are not connected yet. This adds only the
preference and its safe selection contract; no delivery, permission prompts,
download listeners, file opening, or scan authorization is activated. An
authenticated coordinator must independently validate the completed scan report
before using `shouldNotify`. In particular, browser-supplied filename,
metadata and extension-provided outcomes must not be trusted as scan results.

This setting is separate from existing **Show Blocked File Notifications**,
**Show Only Warnings**, **Show Scan Results** and browser monitoring preferences.
It does not change native ClamAV enforcement, file-integrity gates, PDF
destination or unrelated customizations.

CI exercises `tests/download/notify-on-failed-scan.py` and compiles/runs
`test-notify-on-failed-scan.swift` in a disposable isolated UserDefaults
suite, covering explicit opt-in, malformed values, valid results, cancellation,
unrelated preferences, and mandatory warning separation.
