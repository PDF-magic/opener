# OCR must not reintroduce active PDF content (opener-0531)

The optional Maximum sanitized-copy pipeline currently **does not perform OCR**.
It creates raster pixels using the CoreGraphics renderer, reconstructs a new
PDF from only those pixels, validates the final image-only PDF, and requires a
separate scanner pass before any generated copy may be opened. This is not
searchable text restoration or an OCR feature.

OCR is an **untrusted transformation boundary**, not an exemption to the
sanitization policy. If OCR is introduced in the future, it must run **before**
the existing pixel-only reconstruction, or be followed by equivalent
reconstruction and *all* final output checks. In particular, do not attach an
OCR text layer, annotations, forms, actions, embedded files, catalog metadata,
or additional PDF content streams to an already verified copy. Such bytes may
not be offered for save or handed off for a fresh scan.

The final `_passive_pages` gate requires each reconstructed page to draw exactly
one `/Im0` image using the fixed, unfiltered drawing stream emitted by the
pixel-plane writer. Injected OCR operators (including invisible text and
additional streams) fail this gate even if no `/Font` resource was supplied.
Catalog actions, annotations, or attachments are separately denied. Both the
copy-offer flow and `verified_generated_pdf_bytes()` use that validation.
The underlying sanitizer removes untrusted OCR additions by rebuilding only
from decoded pixels; it never copies original PDF objects or OCR dictionaries.

`test-maximum-ocr-safety.py` exercises in-memory OCR text-layer additions,
action/annotation/attachment injection, pixel-only reconstruction, final-offer
rejection, and generated-rescan rejection. The tests run in the existing
sanitized-copy CI on Linux and macOS. This does not enable Maximum protection,
introduce an OCR engine, change user preferences, grant opening permission, or
replace the mandatory ClamAV scan, quarantine and file-integrity checks.
