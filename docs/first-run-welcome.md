# First-run welcome screen (opener-0968)

The standalone SwiftUI **PDF Magic Opener** app shows a welcome screen in its
main window on the first launch, before opening the existing Preferences view.
The welcome first explains the product's purpose in plain language: **when
configured as the user's PDF handler**, PDF Magic Opener requires a verified
local ClamAV clean result and recent signatures before handing a PDF to the
user's chosen application. When verification fails, opening is blocked.
It then explains the existing local scanner gate, the user's selected PDF
application, and where to review settings. It does **not** claim that ClamAV
is installed, that a PDF has already been scanned, or that scans guarantee safety.

Before continuing, the user must explicitly choose **Standard**, **Enhanced**
or **Maximum** as an initial *future-profile preference*. The choice is saved
only when **Continue to Preferences** is selected, using the existing
`preferredProtectionLevel` preference and its schema and safety validation.
Previously selected preferences are displayed without being overwritten. An
invalid or missing choice, unsupported configuration or failed save does not
complete the welcome. The versioned welcome acknowledgement is then recorded
in the **preferences app's own UserDefaults** and the unchanged main Preferences
view opens. Future launches go straight to Preferences. Closing the window
without continuing leaves the welcome pending. The macOS Settings window
remains directly accessible through Command-comma.

This initial choice is **not an active scanner protection profile**. The
currently installed scanner only enforces Built-in ClamAV and fail-closed
handoff. Standard, Enhanced and Maximum have planned controls and cannot be
activated as effective protection until those controls are implemented and
verified.

The welcome neither changes the configured PDF browser nor macOS PDF default,
starts malware scans, provisions dependencies, activates planned protection
policies, updates signatures, or replaces any other user customization. The separate native
PDF handler and its fail-closed scanner admission continue to work independently
even if the user never acknowledges the welcome.

CI tests the native window's wiring and accessible labels, while an isolated
UserDefaults suite verifies first-run, repeat-launch and acknowledgement
behavior without accessing any installed user settings. A separate native
regression tests explicit first-run protection choices, persistence after
restart, and rejection without altering active scanner settings.
