# Conditional Scan History preferences page (opener-0911)

The standalone SwiftUI app now contains a dedicated `ScanHistorySettingsView`
accessible from the existing preferences sidebar **only if its feature owner
explicitly enables the destination**. The `MainPreferencesView` initializer
accepts `scanHistoryEnabled: Bool`, with a **false default** in both existing
app entry points; a hypothetical saved preference, existing operational scan
log, or clean-scan cache must never be interpreted as consent.

When enabled by a future, independently verified feature integration, the
sidebar exposes a labeled **Scan History** destination and a passive page
explaining its availability, privacy, and independent scanner safeguards.
Keyboard next/previous navigation uses only visible destinations. If a stale
history selection is encountered while disabled, the page is not rendered.

This task creates **no** history opt-in toggle, persistence, record-list
viewer, export/clear action, retention policy, or change to existing
operational logging. The collection and opt-in workflow remains separate and
must be implemented and tested before enabling the page in production.
The page itself does not inspect files, databases, or user activity.
The existing Privacy and Logs explanation remains accurate.

The page is registered in the native Xcode target and
`tests/general/scan-history-settings-page.py` runs in required CI. macOS
builds compile the new SwiftUI view alongside the rest of the app.
