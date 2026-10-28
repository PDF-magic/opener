# Block unsupported Maximum sanitization cases (opener-0323)

Maximum's optional rasterized-copy pipeline must **block unsupported or
incomplete sanitization** rather than imply that rendering made a PDF safe.

`maximum_sanitized_copy.assess_sanitized_pdf_copy(source_bytes)` now returns a
frozen `SanitizationDecision` with exactly one of two outcomes:

- **`block`** with a fixed, path-free `SanitizationBlockReason` and no copy
- **`offerForSeparateScan`** with a newly reconstructed, verified in-memory
  `SanitizedCopyOffer`, never permission to open or a malware-clean result

Every outcome has `permits_open=False`, `allow_fallback=False`,
`allow_clean_cache=False`, `preserve_quarantine=True` and
`requires_separate_scan=True`. The serialized decision includes only fixed
status codes and a bounded page count; no source PDF bytes, paths, filenames,
attachments, script text or parser diagnostics enter its metadata.

The following cases are explicitly blocked:

- Input is not a bounded immutable PDF, the converter is missing, the
  source is unreadable/encrypted, or the supported page-count limit is exceeded
- A source needs dynamic rendering or contains an unsupported PDF
  portfolio, optional-content layers, signature permissions/flags or XFA form
- A page contains 3D, rich media, movie, screen or sound annotations that
  cannot be faithfully represented by the supported static raster pipeline
- Page-content or XObject streams use unknown/unsupported filter names or
  contain too many references to validate within the defined bounds.
  Filter *names* are inspected passively; unsupported encoded content is not
  decoded or executed
- Converter process errors, timeouts, empty/oversized output, a returned
  original document, a failed active-content-removal rebuild, or output that
  fails the independent passive-pages validation

Regular JavaScript and attachments remain eligible for the **separate visual
rasterizer**, which strips them; they never enter the output PDF. Only the
complete conversion and passive reconstruction may create a copy offer.
Neither the source nor raw converter output is ever used as a fallback.

The existing `offer_sanitized_pdf_copy(source_bytes)` interface is
preserved: it returns only a verified offer, or `None` for **every** blocked
case. Callers who need a user-visible blocked state or an explainable
workflow decision use the new `assess_sanitized_pdf_copy` entry point.
The existing scanner and user preferences are unchanged. The Maximum profile
remains non-selectable; **no active scanner, viewer or quarantine behavior has
been modified**. A future production Maximum flow must enforce all prerequisite
Enhanced/Maximum controls and rescan any generated copy before opening.

`test-maximum-sanitization-blocking.py` exercises unsupported dynamic
features, unknown stream filters, encryption and malformed inputs, absent or
failed converters, failed/unverified output, forbidden original-document
fallbacks, immutable decision semantics and source-information privacy.
The existing `maximum-sanitized-copy.yml` CI runs the new regressions on
both Ubuntu and macOS alongside the existing native rasterization tests.
Related work in PRs #213 (structural output verification), #214 (generated
copy rescanning), and #215 (safe-copy opening) stays separately scoped.
