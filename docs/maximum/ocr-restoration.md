# Optional OCR restoration is a separate future feature (opener-0530)

## Decision

**Do not restore OCR text in the Maximum sanitized-copy pipeline.** The
existing optional CoreGraphics converter deliberately emits fresh raster-only
PDF pages. A generated copy may preserve visible letters, but cannot promise
searchable or selectable text, accessibility tags, original text coordinates,
or the semantics of the source document. This is an intentional fidelity
tradeoff, not a missing step that the sanitizer should silently reverse.

`SanitizedCopyOffer` now reports `ocrRestored: false` in its fixed, public,
source-independent metadata, discloses that OCR is not included, and rejects
attempts to label the offer as OCR-restored. This is a statement about the
**existing output**, not a toggle to enable OCR. The Maximum profile remains
non-selectable; this change does not add an OCR engine, dependency, UI,
background job or new PDF opening path.

## Separate feature to consider later

A future implementation could offer **explicitly user-initiated**, optional,
local OCR of an already generated and independently verified raster copy.
That would require its own design review, feature gate and tests; it must not
mutate the source, be used to decide whether the source was malware-clean,
or be automatically attached to the sanitized-copy operation. In particular:

- OCR must operate on generated, bounded raster pages, not on original PDF
  objects or metadata, and must not import original text, annotations,
  hyperlinks, scripts, forms, attachments, or hidden source layers.
- A searchable text layer would constitute **new derived content** with
  imperfect recognition, reading-order, coordinate, language and accessibility
  fidelity. Its content should be disclosed as machine-generated and remain
  independently reviewable and discardable. It must never be presented as
  an authenticated recovery of the source document.
- Any resulting PDF is another new artifact requiring strict validation and
  its **own mandatory ClamAV scan and file-integrity checks** before any
  opening or save-to-open handoff. It must never inherit a cached clean
  verdict, permission to open, or removal of quarantine from the source or
  earlier rasterized copy.
- The future OCR worker must have independently reviewed execution,
  filesystem, network, memory, time and output constraints. Document pixels
  and recognized text may contain sensitive material; no external service,
  upload, telemetry or persistent text index should be introduced by default.
  A future opt-in and retention policy need separate review.
- OCR should remain off by default. Users must be able to keep the
  raster-only output without accepting OCR processing or text retention.
  Existing saved scanner preferences and browser choices are unaffected.

Until such a separate feature is designed, implemented and reviewed, the
correct behavior is to keep generated copies image-only and disclose lost
searchability. OCR is **not** a malware scanner, and restoring searchable
text must not weaken isolation or the original scan gate.

## Regression boundary

`test-maximum-ocr-separation.py` verifies the immutable no-OCR offer
contract, fixed public metadata, unchanged scan gate and non-selectable
Maximum profile on both Linux and macOS. On macOS it also uses the actual
compiled CoreGraphics converter with a synthetic searchable source PDF and
asserts the generated PDF contains a raster image but **no searchable text**.
The existing text and scanned-document fidelity suites separately check
visual legibility; those checks must not be mistaken for OCR restoration.
