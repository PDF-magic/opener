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

## First-run browser detection (opener-0972)

While the welcome is visible, it checks for supported browser applications
**registered with macOS** using the same read-only
`DefaultPDFBrowserPreferences.discover()` inventory as the General browser
selector. Discovery validates the exact supported bundle identifiers, real
application bundles and executable presence. It shows the recognizable browser
names, an explicit empty result when none are found, and a checking state. It
does not assert that all installed or unregistered custom browsers are covered.

The inventory is informational only: no browser is opened or selected, no
browser or system PDF preference changes, no permission is requested, and no
scan or network request is started. Existing custom PDF destinations remain
untouched. An installed browser is not proof of compatible PDF handling or an
authorized scanner handoff. The welcome acknowledgement still requires an
explicit **Continue to Preferences** action; discovery never acknowledges it.
The separate native scan, integrity, signature-freshness, and quarantine
requirements remain unchanged.
