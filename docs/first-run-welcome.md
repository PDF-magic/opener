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

Selecting **Continue to Preferences** records the versioned welcome
acknowledgement in the **preferences app's own UserDefaults** and displays the
unchanged main Preferences view. Future launches go straight to Preferences.
Closing the window without continuing leaves the welcome pending. The macOS
Settings window remains directly accessible through Command-comma.

The welcome neither changes the configured PDF browser nor macOS PDF default,
starts malware scans, provisions dependencies, changes protection policies,
updates signatures, or replaces any user customization. The separate native
PDF handler and its fail-closed scanner admission continue to work independently
even if the user never acknowledges the welcome.

CI tests the native window's wiring and accessible labels, while an isolated
UserDefaults suite verifies first-run, repeat-launch and acknowledgement
behavior without accessing any installed user settings.
