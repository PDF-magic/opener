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

The welcome also makes clear that a verified **clean scan** reduces risk but
**cannot guarantee** a PDF is safe: ClamAV may miss unknown or otherwise
undetected threats. It advises opening documents only from trusted sources,
even after verification. This is informational and does not weaken the required
scan gate or claim that an individual file is harmless.

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

## Signature availability check (opener-0976)

On first run, the welcome inspects only metadata for the established installed
ClamAV signature directory and its main/daily .cvd or .cld files. It reports
whether both required nonempty regular files are present, missing/incomplete,
or unsafe/unreadable (including linked files). The user may recheck after
installing or updating definitions; no update starts automatically.

**Presence is not validity, freshness, or proof of a safe document.** This
display-only check never reads the definition payload, runs a scanner, changes
the installed database, or touches existing browser/protection preferences.
The separate PDF scan gate continues to require validated, recent definitions
and a clean scan before authorizing document opening. Native isolated tests
and portable CI wiring checks exercise this behavior.
