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

If the user is offered a change to the macOS default PDF application, they
may decline and keep their current handler. **Continue to Preferences** is
not consent to make PDF Magic Opener the default, and the welcome never
changes the association. The default PDF handler is independent of the user's
chosen post-scan PDF application.

The welcome neither changes the configured PDF browser nor macOS PDF default,
starts malware scans, provisions dependencies, changes protection policies,
updates signatures, or replaces any user customization. The separate native
PDF handler and its fail-closed scanner admission continue to work independently
even if the user never acknowledges the welcome.

CI tests the native window's wiring and accessible labels, while an isolated
UserDefaults suite verifies first-run, repeat-launch and acknowledgement
behavior without accessing any installed user settings.

## Optional Finder Quick Action offer (opener-0979)

On first run, the welcome optionally offers **Configure Finder Quick Action…**.
This expands a setup explanation and links to the existing
[installation instructions](https://github.com/PDF-magic/opener#installation-and-usage).
It explains that the existing installer requires an “Allow and Open” Automator
Quick Action, must be run from a trusted checkout without sudo, and does not
silently replace unrecognized or customized Finder workflows.

Users can choose **Not now** to collapse the instructions or **Continue to
Preferences** without setting up Finder. Viewing the offer or opening its
instructions makes no configuration change and never records the welcome
acknowledgement. Actual Finder setup remains the separate, explicitly invoked
installer and its existing safety checks; the welcome does not launch an
installer, modify files, change scanner policy, or alter user preferences.
