# Select a browser for scanned PDFs

PDF Magic Opener scans a **local PDF** before handing a clean file to a separately
chosen PDF-capable application. **Brave** is the default destination if no
browser preference has been saved. Choosing a post-scan browser is different
from changing your macOS default web browser or the default PDF file handler.

## Use the Settings picker

1. Install the PDF Magic Opener scanning tools, then launch the standalone
   **PDFMagicOpener** preferences application, if available. The shell installer
   installs the scanning handler, **not** the standalone SwiftUI Settings app;
   the latter can also be built using the Xcode scheme described in the
   [README](../README.md).
2. Choose **PDF Magic Opener → Settings…** (or press **Command-comma / ⌘,**)
   and open **General**.
3. Under **Default PDF browser**, open **Browser for scanned PDFs** and choose
   an installed browser. The list contains discovered, registered, executable
   supported browsers; it does **not** automatically choose a replacement.
4. Wait for **Default PDF browser saved.** before treating the change as
   successful. The installed application chooser independently verifies PDF
   eligibility before atomically writing the selected bundle identifier to
   `~/Library/Application Support/Studio/allow-and-open/target-app.txt`.
   If you see **Could not verify or save that browser**, the previous choice
   remains unchanged. Confirm the helper and browser are installed and eligible.
5. Reopen **General** to check the current selection. A custom or unavailable
   existing selection may display as **Existing selection (not in installed
   browser list)**; viewing the page does not discard that choice.

The **Browsers** sidebar is informational; its installed-app list does not save
a destination. **Set as Default PDF App** in General instead controls whether
macOS sends local PDF opens to the PDF Magic Opener *scanning handler*, not
which browser receives a PDF after a successful scan.

## Select a custom installed application

If your browser or PDF viewer does not appear in the supported Settings list,
use the **installed verified chooser**. It opens the native macOS `.app` picker:

```sh
python3 "$HOME/Library/Application Support/Studio/allow-and-open/select-custom-pdf-application.py"
```

Or specify an installed application explicitly:

```sh
python3 "$HOME/Library/Application Support/Studio/allow-and-open/select-custom-pdf-application.py" --application "/Applications/Custom Browser.app"
```

The chooser verifies the exact registered application and PDF capability
**before** atomically saving its bundle ID in `target-app.txt`. If you cancel,
or verification fails, your previous choice is preserved. For an app on
another volume, register it with macOS Launch Services first so its exact
installation can be verified. The terminal's separate numbered browser
selector is **read-only** and cannot save a choice by itself; see the
[README's PDF target application section](../README.md#pdf-target-application)
for its technical input format and the advanced opt-in
`system-default-browser` setting.

## Verify the scan gate remains active

To scan a local PDF on double-click, macOS must separately be configured to
open PDFs with the **installed PDF Magic Opener scanning handler**. Otherwise
choose **Open With → PDF Magic Opener** in Finder. A browser's inline PDF
viewer may bypass this native local-file flow; see
[unsupported browser PDF routes](browser-unsupported-routes.md).

Every PDF passed through PDF Magic Opener still requires its ClamAV scan,
signature-freshness and file-integrity checks, quarantine safeguards, and
post-scan destination verification. A missing, untrusted, or ineligible
selected browser **blocks opening**: it never triggers a silent fallback,
bypasses scanning, or resets your saved preference. Do not disable those
checks to resolve a failed selection.
