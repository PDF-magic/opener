# Large valid PDF security corpus (opener-1041)

The security corpus includes two deterministic **valid PDF 1.4** documents,
generated on demand by [`large_valid_pdf_corpus.py`](../../large_valid_pdf_corpus.py)
and materialized only in a disposable directory by the
[`large-valid-corpus.py` tests](../../tests/pdf/large-valid-corpus.py):

- **`single-large-stream.pdf`**: one page and a real, uncompressed content
  stream containing over 17 MiB of inert PDF whitespace after visible text.
- **`many-large-pages.pdf`**: 256 pages, each with its own content stream and
  64 KiB of inert stream whitespace; the file exceeds 16 MiB.

These are not truncated files, deceptive trailer padding, external downloads,
or antivirus samples. The generator writes complete indirect objects, exact
stream lengths, a conventional cross-reference table with correct object
offsets, a catalog, page tree, and a final `%%EOF`. The tests verify the
actual size, deterministic distinct bytes, each cross-reference offset, strict
`pypdf` opening, page counts, and selected page streams. No fixture contains
PDF actions, embedded files, scripts, external URLs, or executable payloads.

Both examples intentionally exceed the **16 MiB** limit of the optional
structure-inspection stage, which must return a non-authorizing `sizeLimit`
result **even though the files are valid PDFs**. This is a resource-budget
boundary, not evidence that a document is corrupt or dangerous. Strict parsing
in the test harness is separate from production scanner admission. No file is
passed to a native opener, and no change is made to ClamAV, quarantine,
preferences, or existing baseline profile test fixtures.

Run the focused tests from the repository root:

```sh
PYTHONPATH=. python3 tests/pdf/large-valid-corpus.py -v
```

The existing `scanner-tests` GitHub Actions job runs the same tests after
installing the pinned `pypdf` dependency.
