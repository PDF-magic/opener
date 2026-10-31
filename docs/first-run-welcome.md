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

The welcome also offers an optional **Set PDF Magic Opener as Default** button.
Only selecting that button invokes the already installed, verified PDF handler
registration helper. The helper rejects missing or invalid installations and
requires a successful Launch Services read-back before reporting success. A
failed setup shows a message and leaves the welcome available; it never claims
the PDF association changed. This action does not replace the chosen PDF viewer
or alter scanner policy. **Continue to Preferences** skips the optional action.

If the user is offered a change to the macOS default PDF application, they
may decline and keep their current handler. **Continue to Preferences** is
not consent to make PDF Magic Opener the default, and the welcome never
changes the association unless the user explicitly selects the separate
default-action button. The default PDF handler is independent of the user's
chosen post-scan PDF application.

Selecting **Continue to Preferences** records the versioned welcome
acknowledgement in the **preferences app's own UserDefaults** and displays the
unchanged main Preferences view. Future launches go straight to Preferences.
Closing the window without continuing leaves the welcome pending. The macOS
Settings window remains directly accessible through Command-comma.

Simply displaying or continuing past the welcome does not change the configured
PDF browser or macOS PDF default, start malware scans, provision dependencies,
change protection policies, update signatures, or replace user customizations.
The macOS PDF association can change only through the separate explicit button. The separate native
PDF handler and its fail-closed scanner admission continue to work independently
even if the user never acknowledges the welcome.

CI tests the native window's wiring and accessible labels, while an isolated
UserDefaults suite verifies first-run, repeat-launch and acknowledgement
behavior without accessing any installed user settings.
