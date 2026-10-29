# Annotated-document fidelity regression (opener-0524)

This **test-only** regression covers documents containing interactive and
markup annotations when passed to the optional Maximum visual-only sanitized
copy converter. It uses two deterministic synthetic pages with distinct
color blocks and fine rules. Each source page has two real PDF annotations:

- Page 1: a link annotation carrying a URI action, and a highlight annotation
  with a separate `/AP /N` Form XObject appearance stream.
- Page 2: a sticky text-note annotation and a FreeText annotation with a
  separate appearance stream and declared text appearance settings.

The source is inspected with strict pypdf parsing to prove `/Annots`
references, types, actions and appearance streams are real PDF objects and
separate from page `/Contents`. Private-looking fixture strings and a
non-resolving example URL are never fetched. No real user PDFs are required.

## What fidelity means for this lossy converter

The existing converter deliberately **does not preserve annotations**.
Page artwork underneath annotations should remain visibly positioned and
colored, but link actions, note contents, annotation dictionaries, interactive
behavior, and selectable annotation metadata must not be carried to the
generated raster-only PDF. Appearance streams are *not guaranteed* to survive;
this test does not claim annotation markups remain visible, nor does it pretend
to preserve or reconstitute editable annotations.

On Linux and macOS, synthetic Pillow reference images and negative controls
reject blank/erased/shifted/swapped page content. On macOS, CI compiles the
actual CoreGraphics sanitizer and calls
`maximum_sanitized_copy.offer_sanitized_pdf_copy` **without mocking it**.
The test inspects the returned PDF and its actual image pixels: both pages
retain geometry, order, distinct visual color landmarks and fine strokes,
but contain no `/Annots`, link actions, or searchable text. The fresh result
has one 2× raster image per page, `permits_open=False`, and
`needs_separate_scan=True`.

These checks do not prove that every PDF annotation will display correctly.
The tests make the intentional loss of interactive and annotation appearance
data explicit rather than claiming complete semantic fidelity.

No scanner or converter code changes in this task. The existing mandatory
ClamAV scan, quarantine, signature, clean-cache, user preference and
application-handoff protections remain unchanged. Maximum remains
unselectable. A generated copy still requires a fresh scan and passing tests
never constitute a malware-clean verdict or opening permission.
