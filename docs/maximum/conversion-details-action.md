# View Conversion Details action — opener-0555

In the macOS **Protection** settings page, select the planned **Maximum**
preview and activate **View Conversion Details**. The button opens an
accessible, dismissible sheet with plain-language information about the
future sanitized PDF conversion. It is intentionally not shown for Standard
or Enhanced previews.

The sheet explains:

- A supported source would be rendered as flattened page images in a
  **separate visual-only PDF**, with the original remaining unchanged.
- Text search and selection, links, interactive forms, annotations,
  attachments, scripts and metadata may be removed. OCR is not restored,
  digital signatures may be invalidated, and some visual details can change.
- Conversion itself is never a malware-clean verdict. A generated PDF needs
  a separate fresh scan and verified launch, and failures cannot fall back
  to opening the original.

These are **general conversion characteristics**, not per-document results
or a claim that the installed application performed conversion. The
currently enforced Built-in ClamAV policy is unchanged and the Maximum tier
remains unavailable; no PDF is inspected, opened, converted or written by
this display-only action. It accepts no PDF-controlled text, filenames,
paths or diagnostics.

The focused regression test is run by existing scanner CI, and the
native macOS build compiles the actual SwiftUI button and details sheet.
The companion Maximum interface tasks for sanitization progress, identity,
capability-loss previews and save/view actions remain independent.
