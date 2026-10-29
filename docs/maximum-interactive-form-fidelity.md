# Interactive-form document fidelity (opener-0525)

This test-only regression exercises the optional Maximum rasterized PDF copy
with real AcroForm text, checkbox and choice fields. The goal is **visual
fidelity of the underlying pages plus intentional removal of interactivity**,
not preservation of editable form fields.

The deterministic synthetic two-page PDF contains a real catalog `/AcroForm`
with three separate `/Fields` entries, `/Tx`, `/Btn`, and `/Ch` values,
widget annotations in each page's `/Annots`, and distinct widget appearance
streams. The checkbox includes `/AP /N /Off` and `/Yes`, and the choice
field includes `/Opt`. Field names and values are synthetic private-looking
strings so tests can check that original PDF metadata is not carried into the
newly generated document. No real user data or network requests are used.

Both Linux and macOS CI verify that these are actual editable source fields,
not placeholders painted into page content. Pixel-based reference images and
negative controls reject missing page colors, missing fine rules, blank pages,
shifted artwork and swapped page order.

On **macOS**, the test compiles the real CoreGraphics sanitizer and invokes
`maximum_sanitized_copy.offer_sanitized_pdf_copy` without mocking conversion.
It inspects the resulting PDF and pixels, checking that both pages retain
geometry, order, distinct color landmarks and the underlying horizontal
rule. The new PDF must contain one raster image per page, no searchable text,
no `/AcroForm`, no `/Annots`, no editable fields, and no private form metadata.

**Intentional loss:** this visual-only conversion strips form interactions,
field names, values and widgets. Whether a viewer renders a particular widget
appearance or filled value into pixels is **not guaranteed**; these tests do not
assert preservation of entered form values, accessibility, tab order, field
validation, submitted actions or any arbitrary form's appearance. The form
rectangles and source page content are distinct, allowing the test to measure
underlying artwork without mistaking a lost widget for an intact control.

No renderer or scanner implementation changes are made. Maximum remains
nonselectable; a generated sanitized copy still needs a fresh ClamAV scan and
never authorizes opening. Existing mandatory scanner checks, quarantine,
signature integrity, clean cache, destination handoff and user preferences
are preserved.
