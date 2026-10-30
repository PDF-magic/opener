# Show Only Warnings download preference (opener-0731)

The **Browsers** settings page exposes a user-controlled **Show Only Warnings**
toggle under **Download warning display**. It defaults **off** so existing
optional informational and clean-scan summaries remain visible. The setting is
independent of the separately scoped **Show Scan Results** preference in
opener-0730; neither preference is authority to skip a scan or hide safety
warnings.

`DownloadWarningOnlyPreference` reads and saves only the boolean
`showOnlyWarnings` key in the existing isolated app preference suite.
Missing and malformed values resolve to off (visible summaries) without
changing stored data. Saving rechecks persistence; failed saves restore the
previous value. Opening this page never saves settings or initiates scanning.

When the future independently authenticated native download-scan reporting
integration is implemented, its **verified classification** may call
`shouldPresent` with `.verifiedCleanSummary` or
`.verifiedInformationalSummary`: these optional presentations are hidden
when the toggle is on. **Security warnings, scan failures, incomplete scans,
unknown outcomes, and blocking decisions always remain visible** regardless
of the toggle. The source must never classify browser-supplied MIME, filenames,
download states, or alleged clean results as a verified scanner verdict.
The native scanner's ClamAV verification, fresh signatures, identity and
integrity checks, quarantine retention, fail-closed opening, and user's PDF
application choice are unaffected.

Browser download scanning and report presentation are **not yet active**:
this is an explicit user preference and safe native presentation-filter
contract, not a working browser-to-native integration. It does not change
extension permissions, background activation, scanner executables, the
Show Scan Results setting, or existing user customizations.

CI runs both `tests/download/show-only-warnings.py` (source and safety
boundary checks) and `test-show-only-warnings.swift` (compiled preference
persistence and filtering with an isolated disposable UserDefaults suite).
