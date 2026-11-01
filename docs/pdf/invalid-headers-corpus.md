# Invalid PDF header corpus (opener-1029)

`INVALID_PDF_HEADERS` in `reference_pdf_collection.py` provides nine
deterministic, harmless negative inputs derived from the first valid reference
PDF. Only its nine-byte header is replaced; the PDF objects, cross-reference
table, trailer and EOF are preserved byte-for-byte.

The collection includes missing/wrong magic, a leading byte-order mark,
unsupported version numbers, nonnumeric and non-ASCII versions, and invalid
header terminators (space and NUL). It deliberately leaves
`REFERENCE_PDFS` unchanged: those six files remain the valid, shared baseline
for protection-profile admission tests.

`tests/pdf/invalid-headers-corpus.py` validates all samples against the
read-only format identifier (including misleading `.pdf` filenames), verifies
that strict structure parsing reports failure without authorization, checks
immutability and unique bytes, and preserves the valid-corpus and scanner gate.
The required CI `scanner-tests` job runs this regression with no additional
dependencies or external sample downloads.

These are **test fixtures**, not live malware detection or evidence that any
planned Standard, Enhanced or Maximum profile is active. Format identification
never authorizes opening. The installed ClamAV, file-integrity, cache and
quarantine controls are unchanged.
