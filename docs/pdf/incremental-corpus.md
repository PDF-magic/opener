# Incremental-update PDF reference corpus — opener-1034

The in-memory `INCREMENTAL_REFERENCE_PDFS` collection in
`reference_pdf_collection.py` contains three deterministic, innocuous
PDF 1.4 documents. They are complete documents, not partial xref fragments:

- `incremental-added-metadata`: a second revision indexes new metadata
  object 6 and makes it the PDF Info dictionary.
- `incremental-replaced-font`: a second revision replaces existing font
  object 5 with Courier while retaining the original page content.
- `incremental-two-updates`: three revisions add object 6 and then
  replace object 5. Both earlier revision trailers remain intact.

Each appended revision has its own xref section, trailer, `/Prev` link,
`startxref` and `%%EOF` marker. The earlier bytes are unchanged.
`tests/pdf/incremental-corpus.py` validates strict parsing, visible
final objects, actual revision counts and added/replaced object evidence.
It also verifies that damaged revision links fail closed.

Existing `REFERENCE_PDFS` remains an unchanged six-item, single-revision
baseline for protection-profile tests. Scanner outcomes on these fixtures
are simulated, not live antivirus determinations. The corpus does not
contain scripts, launches, embedded executables, or malware samples;
it does not authorize opening a PDF or change scanner configuration,
quarantine, profile availability, or user preferences.

Run from the repository root after installing `pypdf==5.9.0`:

```sh
PYTHONPATH=. python3 tests/pdf/incremental-corpus.py -v
```
