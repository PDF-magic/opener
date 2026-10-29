# Persist the user's planned protection preview (opener-0336)

The Protection Settings cards **save their selected preview immediately** after
a successful user action, and reload it on the next appearance of Settings.
A visible status explains success or a failed save. There is no hidden Apply
button or ambiguous unsaved pending state. The UI never falsely reports a
failed write as durable.

The durable preference is the separate `preferredProtectionLevel` contract
introduced by [PR #224](https://github.com/PDF-magic/opener/pull/224).
`PlannedProtectionLevelPreference.saveExplicitChoice` verifies the installed
configuration schema and Built-in active policy, synchronizes the same
UserDefaults suite, validates the saved tier and rolls back failed writes.
The view maps only the three known Standard, Enhanced and Maximum preview
choices to `PreferredProtectionLevel`; a saved unknown/future choice is left
untouched when the page loads. Existing Standard choices and unrelated
preferences are retained.

**This is preview persistence, not an active security-level change.**
The installed PDF opener still enforces only Built-in ClamAV and fail-closed
opening. The currently planned named tiers are not selectable for enforcement;
neither this UI nor the preference ever switches the scanner or the native
PDF-opening pipeline. A separate prerequisite is the completed,
safe activation of the named profiles; the UI must be updated when that
scanner capability becomes available.

CI checks presentation contract on Linux, builds the complete SwiftUI app on
macOS, and launches the same isolated Swift test executable as multiple
independent processes to verify Standard/Enhanced/Maximum round-trips after
actual restarts. Invalid/future choices, failing writes, old installations,
profile-schema conflicts, General reset and unrelated custom browser
preferences are tested without touching real user data.
