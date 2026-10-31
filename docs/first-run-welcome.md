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

The first-run screen also offers an optional **Default PDF browser** picker
using the same installed-browser discovery and verified atomic chooser as
General preferences. Its initial selection reflects the saved PDF destination,
including a custom or unavailable selection without replacing it. Selecting a
browser in the picker does not save anything. Only an explicit **Save browser
choice** action invokes the existing installed verifier, and failures leave the
previous selection unchanged. The chooser needs the installed PDF Magic Opener
helper; if it is unavailable, saving fails without weakening scan protections.
The picker never changes the macOS default PDF handler. Users may skip it and
continue with all settings untouched.

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

If the user is offered a change to the macOS default PDF application, they
may decline and keep their current handler. **Continue to Preferences** is
not consent to make PDF Magic Opener the default; only explicitly selecting the separate default-handler action may change the association. The default PDF handler is independent of the user's
chosen post-scan PDF application.

Without an explicit, verified browser save or separate default-handler action, the welcome neither changes the configured
PDF browser nor macOS PDF default,
starts malware scans, provisions dependencies, activates planned protection
policies, updates signatures, or replaces any other user customization. The separate native
PDF handler and its fail-closed scanner admission continue to work independently
even if the user never acknowledges the welcome.

CI tests the native window's wiring and accessible labels, while an isolated
UserDefaults suite verifies first-run, repeat-launch and acknowledgement
behavior without accessing any installed user settings. A separate native
regression tests explicit first-run protection choices, persistence after
restart, and rejection without altering active scanner settings.

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

## Optional browser extensions (opener-0980)

The first-run welcome explains that browser extensions are **optional**: the
installed native PDF handler can perform its existing verified local scan
workflow for PDFs opened through that handler without any browser extension.
Choosing a browser as a post-scan destination is distinct from installing a
browser extension.

Current browser extension packages are **inactive scaffolds**. They have no
verified browser-to-native-scanner connection and cannot scan, sanitize, or
open PDFs. Installing or enabling one does **not provide an automatic PDF scan**
or protection for files rendered directly by a browser PDF viewer. Users are
free to continue without extensions. First-run setup neither installs or
enables extensions nor requests browser permissions or changes browser
preferences; any future extension installation, enabling, or permission grant
is a separately controlled user action. No feature is offered as active.

The informational, accessible first-run section does not run a browser,
request permissions, write to existing settings, or change the scanner's
fail-closed checks. Required CI already invokes
`tests/general/first-run-welcome.py`; regressions verify this text against
the inactive browser manifest, background and native connection status.

## Extension setup instructions (opener-0981)

The first-run **Optional browser extensions** section now displays concise,
accessible setup guidance without implying that an extension is required or
that a functioning, publicly distributed browser integration exists:

1. **Safari, development/test builds:** Only after installing a properly
   signed host app containing the Safari extension, open
   **Safari > Settings > Extensions**, locate PDF Magic Opener, and enable it manually if desired.
   If the extension does not appear, check the installed host app rather than
   bypassing macOS signing or Safari protections. The host app's embedded
   extension is not automatically enabled.
2. **Chrome, Edge, Firefox, and other browsers:** There is **no public release**
   ready to install. The browser packages are development/test artifacts,
   not production PDF protection. This welcome does not direct users to an
   unverified store listing or ask them to sideload an unsigned artifact.
3. **After enabling a test extension:** Its toolbar still reports **Not
   active**. It cannot scan, approve, or open PDFs, and no verified
   browser-to-scanner connection exists. For scanned PDF opening, use the
   installed native PDF handler.

The welcome neither starts extension installation or activation nor requests
browser permissions, opens browser settings, changes the user's PDF browser
choice, or affects mandatory local scanner checks and quarantine protections.
The existing required portable first-run CI suite verifies the instructional
text, accessible heading, read-only behavior, Safari documentation, inactive
extension manifest, and lack of publicly released extension artifacts.

## Basic installation health check (opener-0982)

The first-run welcome now performs a **read-only basic installation check**
when it first appears. Users may repeat the inventory with **Check
Installation Again**. It reports the native PDF Magic Opener scan-handler
bundle's expected identity, PDF declaration and executable; the presence,
incompleteness or unsafe metadata state of required ClamAV definition files;
and whether macOS currently associates PDFs with the PDF Magic Opener
handler, another application, or an unknown default.

An alternate macOS PDF default is a user choice, **not** permission to change
that association. A missing scan-handler bundle or absent/unverifiable
definition files produce an actionable message, not a claim of healthy
protection. Even a positive basic inventory **does not** validate ClamAV
installation/version, signature freshness/content, file integrity, quarantine,
scanner execution, a clean PDF verdict, or authorization to open a document.
A separate in-progress checklist task, opener-0975, inspects ClamAV
installation; the health inventory intentionally does not duplicate its
scanner lookup.

This check runs no process, scanner, installer, updater or network operation,
and writes no settings. It does not accept PDFs, alter the macOS PDF default,
or change existing browser/protection customizations. The actual installed
scanner's fail-closed checks remain authoritative. The existing required
scanner-tests and macos-build CI jobs now run portable wiring checks and
native isolated status-matrix tests, respectively.

## Optional default PDF handler offer (opener-0977)

An independent, optional **Set PDF Magic Opener as Default** button lets users
explicitly register the installed scanner-gated PDF handler as the macOS default.
It reuses the existing validated handler action and reports success only after
Launch Services read-back confirms the association. A missing or invalid handler
shows a failure message, without modifying the chosen PDF viewer, browser
selection, signature database, or scan policy.

Continuing to Preferences without selecting this action preserves the existing macOS PDF association, scanner requirements, and user-selected browser.
