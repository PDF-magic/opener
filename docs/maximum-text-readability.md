# PDF text readability after conversion (opener-0515)

The existing optional Maximum CoreGraphics converter produces new raster-only
PDF pages. This task adds a **real macOS regression test** for visible text
fidelity; it does not alter conversion, enable Maximum, or promise OCR.

## What is tested

`test-maximum-text-readability.py` constructs a two-page synthetic source
PDF with standard Helvetica vector text at **8, 10, and 14 points**, plus a
distinct second-page sentence. The source is verified to contain searchable
text using the existing pinned pypdf parser. The test then calls the real
`offer_sanitized_pdf_copy` CoreGraphics path compiled by CI, inspects the
actual returned PDF, and verifies every output page has an in-memory raster
image at the converter's bounded **2×** resolution.

For every known line position, the test measures **dark-glyph pixel coverage,
columns occupied by ink, and horizontal light-to-dark transitions**. These
image-detail proxies detect empty, faint, badly blurred, or replaced-by-solid-
block text regions without OCR and without retaining any source filename or
document contents in reports. Their thresholds are deliberately conservative
across CoreGraphics rasterization versions and are checked with negative
unit fixtures for blank, blurred, faded, and solid-filled images. A legibility
proxy cannot prove semantic readability for arbitrary PDFs: these tests
validate specific deterministic samples, not universal accessibility.

The test also confirms that the converted document has no searchable/selectable
text, as intended by visual-only rasterization; **visible readability** and
**text searchability** are different properties. The offer still
`permits_open=False` and requires a separate scan.

## Coverage and safety

The existing `.github/workflows/maximum-sanitized-copy.yml` runs fixture
and metric self-tests on Linux and macOS, and runs the **real conversion**
readability assertion on macOS after compiling the native Swift converter.
Neither the scanner nor the converter has been changed. This is a test-only
Maximum fidelity check, not an active inspection gate: existing ClamAV,
quarantine, signature, clean-cache, network and filesystem safeguards and
user customizations remain unchanged.

If test glyph detail is lost in a future converter update, the macOS CI job
fails. The tests never write converted documents, launch PDF viewers, run OCR,
alter preferences, remove quarantine, or declare input safe.
