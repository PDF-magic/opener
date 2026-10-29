# Validate sanitized PDF structure before offering a copy (opener-0319)

The optional Maximum `offer_sanitized_pdf_copy()` flow now requires an
**independent structural check of its final generated PDF bytes**, after the
existing passive-page check and before constructing any `SanitizedCopyOffer`.
If the final output is incomplete, structurally contradictory, unsupported,
or malformed, the helper returns no offer. It never falls back to returning
the input PDF.

`maximum_sanitized_structure.verify_sanitized_pdf_structure(pdf_bytes,
expected_pages)` performs bounded, strict parsing with `pypdf==5.9.0`:
it requires a valid PDF header and final `startxref`/`%%EOF` framing,
a real classic cross-reference table at the declared offset, matching
indexed indirect-object headers, resolvable objects, a valid root and
acyclic parent-linked page hierarchy, consistent /Count values, bounded
finite page geometry, and the exact expected number of pages. Optional
page content streams must resolve to streams; raw streams have a strict
size ceiling, and Flate-compressed content is expanded only with a
bounded decoder that rejects truncated or invalid compressed data.

The validator rejects repair-dependent, encrypted, incremental and
object-stream outputs, unsupported content filters, invalid page trees,
trailing garbage, oversized files and excessive objects/streams. Its
fixed failure message never includes source PDF strings, file paths,
commands or source exception text. Successful evidence consists only of
a page count and object count with `permits_open=False`. Structural
validity alone is **not** a guarantee that the raster pixels are safe or
that the resulting PDF is malware-free.

The check operates on the **final copy** regardless of whether the
raster-to-raster reconstruction in concurrent
[opener-0315 PR #212](https://github.com/PDF-magic/opener/pull/212)
is present; no such reconstruction is duplicated here. It does not
replace active-content removal, isolated rendering, the separate ClamAV
scan of generated output, or the user-confirmed save flow. Maximum is
still non-selectable; the installed Built-in scanner, signature updates,
quarantine, cached verdicts, file-integrity verification and custom
PDF viewer preferences remain unchanged.

The dedicated
`test-maximum-sanitized-structure.py` and cross-platform CI workflow
validate complete and multi-page PDFs, corruption of xref offsets,
page-tree mismatch, truncated streams, malformed framing, encryption,
overlarge outputs and invalid input types. macOS CI additionally checks
actual native CoreGraphics conversion. No untrusted PDF bytes are
executed or written to disk by the verifier.
