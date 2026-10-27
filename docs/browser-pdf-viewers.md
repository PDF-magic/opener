# Browser PDF viewer differences

PDF Magic Opener **scans and verifies a local PDF before handing it to the
selected macOS application**. It does not render PDFs, supply a common PDF
viewer, or replace the chosen browser's settings. Reading, filling forms,
annotating, printing, and saving are controlled by the destination application.

## Compare browsers and viewer families

| Browser | macOS bundle identifier | PDF viewer and practical differences |
| --- | --- | --- |
| Brave (default) | `com.brave.Browser` | Chromium-derived viewer, subject to Brave's own PDF preferences; the opener's default has no extra editing privileges. |
| Google Chrome | `com.google.Chrome` | Chrome's PDF viewer documents search, forms, annotations, drawing, and on-device OCR for scanned PDFs; feature availability varies with Chrome versions and settings. |
| Chromium | `org.chromium.Chromium` | Open-source Chromium-family viewer; do not presume that every Google Chrome-only tool is present. |
| Microsoft Edge | `com.microsoft.edgemac` | Chromium-derived viewer with Edge-specific PDF controls and preferences; the toolbar need not match Chrome's. |
| Vivaldi | `com.vivaldi.Vivaldi` | Chromium-derived viewer, with PDF handling and download settings set by Vivaldi. |
| Opera | `com.operasoftware.Opera` | Chromium-derived viewer; viewer UI and feature rollout can differ from Chrome. |
| Arc | `company.thebrowser.Browser` | Chromium-derived PDF rendering presented in Arc's browser UI and navigation model. |
| Mozilla Firefox | `org.mozilla.firefox` | Built-in **PDF.js** reader rather than Chromium's viewer; supports forms, text/drawing annotations, highlights, and visible signature marks. |
| Apple Safari | `com.apple.Safari` | PDF display in Safari's macOS interface; **Preview** is a separate app for more extensive Markup and page rearrangement. |

These identifiers are **installed application bundle IDs**, not commands or
promises that every browser is supported on every Mac. Chromium-derived
browsers share a lineage, but their viewers are **not identical**: feature
availability, policies, menus, and download defaults may diverge.

## What changes when you switch PDF viewers?

- **Navigation and display:** Search, zoom, page fitting, outlines, printing,
  keyboard shortcuts, and rotate controls may be in different menus.
- **Forms, annotations, and signatures:** Firefox PDF.js documents form
  filling, highlights, drawing, and signature annotations. Chrome documents
  form filling, highlighting, drawing, and signing. Other Chromium-family
  browsers may expose a different subset. A visible signature annotation
  is not necessarily a cryptographically verified digital signature.
- **Image-only/scanned PDFs:** Chrome documents on-device OCR making scanned
  text searchable. Do **not** assume equivalent OCR in Chromium, Brave, Edge,
  Vivaldi, Opera, Arc, Firefox, or Safari; test the installed viewer.
- **Open in tab or download:** Each browser has its own PDF-viewing, download,
  and sometimes administrator-controlled preferences. Choosing that browser
  in the opener does not override those preferences. A successful application
  handoff does not guarantee an in-tab view.
- **Save behavior and privacy:** Browser annotations and saving are managed
  by the viewer. PDF Magic Opener does not change PDF contents or upload them.
  Browser-specific cloud or synchronization functions have their own settings.

## What stays the same in PDF Magic Opener?

See [PDF target application](../README.md#pdf-target-application) for configuring
the destination. Brave remains the fallback when no application setting exists,
and installing updates does not overwrite an existing user selection.

The **ClamAV verdict, file-integrity, quarantine, and local-file-availability
gates** apply regardless of browser. The
[PDF target verifier](../verify-pdf-target.swift) requires the selected
application to be registered for PDF opening or satisfy a **specific verified
exception**. Some browsers display PDFs without macOS PDF-handler registration,
but a built-in viewer alone cannot bypass verification. The
[native launcher](../launch-scanned-file.swift) additionally checks the
installed application's identity and executable. Failed verification must
stop opening, **not fall back** to an unchecked handler or invoke the opener
recursively.

If the scan succeeds but the document does not display, confirm that the
selected browser is installed, passes PDF capability verification, and has
its own PDF viewer enabled. Test searchable, image-only, fillable, and
annotated sample PDFs before relying on any viewer-specific feature. Apple's
separate Preview app may be better suited to editing or rearranging pages.

## Vendor documentation

- [Google Chrome — Manage PDFs](https://support.google.com/chrome/answer/16215622?hl=en)
  describes viewer navigation, form controls, annotations, and OCR.
- [Mozilla Firefox — View and edit PDFs](https://support.mozilla.org/en-US/kb/view-pdf-files-firefox-or-choose-another-viewer)
  describes the PDF viewer, annotations, forms, and visible signatures.
- [Mozilla PDF.js](https://github.com/mozilla/pdf.js)
  identifies the rendering library integrated into Firefox.
- [Apple — Preview for Mac](https://support.apple.com/guide/preview/get-started-prvw846b61d3/mac)
  describes the separate macOS app's PDF editing and Markup functions.

These resources describe their respective products, not promises of feature
parity or of approval by PDF Magic Opener.
