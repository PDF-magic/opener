# Optional PDF structure parser (opener-0283)

The comparative selection and memory evaluation for opener-0406 is in
[PDF parser evaluation](pdf-parser-evaluation.md). The current version pin
is retained deliberately; it is not an unreviewed dependency upgrade.

The `pdf_structure_parser.parse_pdf_structure(bytes)` entry point uses the
maintained, pinned [pypdf](https://pypi.org/project/pypdf/) library to **parse
real PDF cross-reference tables, catalog objects, and page trees** in strict
mode. It returns a frozen PDF version and page count, not a clean/malware
verdict. The dedicated regression test parses the existing safe reference PDF
collection and pypdf-generated documents.

Install this *optional* dependency with
`python3 -m pip install -r requirements-enhanced-pdf.txt`. The pinned version
was reviewed against the 2026-10-27 release; regularly update this pin after
security review.

**Current boundary:** Standard, Enhanced, and Maximum profiles are not yet
selectable. The installed Built-in ClamAV scanner **does not call this
parser**. It retains the existing signature freshness, integrity rechecks,
timeout, quarantine and verified handoff. A future Enhanced-profile
integration must package the dependency, keep the scanner mandatory, and
enforce its own per-stage time/memory budget before enabling the parser on
untrusted files.

The parser accepts immutable in-memory bytes only and refuses an unavailable
dependency, invalid PDF header or EOF, encrypted documents, parsing errors,
empty page trees, more than 1,024 pages or more than 16 MiB of input. Errors
are fixed, path-free and fail closed. It intentionally does **not** execute
JavaScript, decode arbitrary page content or embedded attachments, launch
files, change preferences, or grant permission to open a PDF. Structure parsing
is not a comprehensive malware or PDF-feature-security assessment. Input-size
limits alone do not enforce CPU/memory bounds against adversarial PDFs; future
integration must isolate parsing and enforce the separately planned resource
and duration limits.


### Cross-reference and object-stream parsing (opener-0416)

The existing strict `PdfReader` can resolve traditional `xref` tables, PDF 1.5
`/Type /XRef` streams (including Flate-compressed entries), and `/Type /ObjStm`
object streams. Compressed page dictionaries must be resolved through the
object-stream index before the page tree can be counted and its `/Page`
objects validated. These are **parser capabilities**, not evidence that every
unrelated stream or unused object has been inspected.

`test-pdf-cross-reference-parsing.py` generates harmless, bounded PDFs in
memory, with exact byte offsets and independently checkable xref entries.
It exercises a traditional table, uncompressed and Flate-compressed xref
streams, and page dictionaries stored in object streams, plus malformed
cross-reference/stream indexes that must fail closed. The test is included
in the existing `scanner-tests` CI job that pins the pypdf dependency.

The separate `pdf_object_relationships.py` stage continues to reject
object streams pending its own graph-validation scope; this task does not
relax that restriction. Neither parser is wired into the installed Built-in
ClamAV gate, which retains its mandatory safety and handoff checks.

## Structured parser output (opener-0413)

A successful `parse_pdf_structure(pdf_bytes)` call returns the frozen
`PDFStructure(pdf_version, page_count)` evidence object. Consumers that need
stable, JSON-compatible data can call `PDFStructure.to_dict()`:

```json
{
  "schemaVersion": 1,
  "pdfVersion": "1.4",
  "pageCount": 1,
  "authorizesOpen": false
}
```

This **version 1 contract** contains exactly the four keys shown above.
`pdfVersion` is the recognized header version (PDF 1.0–1.7 or 2.0),
`pageCount` is an integer in the inclusive range 1–1,024, and
`authorizesOpen` is always false. Direct construction of evidence rejects
unknown versions, non-integer page counts (including booleans), and out-of-range
values. The returned dictionary is detached from the immutable evidence.

**No parsed document contents, raw PDF strings, filenames, URLs, object streams,
attachment names, or exception messages are included.** A rejected, oversized,
encrypted, or malformed document raises the existing fixed-message
`PDFStructureParseError`; it never produces a successful output record.
This is *structural evidence only*: not a malware verdict, a complete PDF
security assessment, or permission to open or cache a document. Additional
inspectors can produce their separately defined findings without extending
this minimal parser record or activating the planned Enhanced profile.

## Structured parsing-failure results (opener-0430)

Call `parse_pdf_structure_result(contents)` when a caller needs a
**machine-readable failure rather than an exception**. A successful parse
returns the same frozen `PDFStructure` evidence and existing
`to_dict()` schema as `parse_pdf_structure`. A failed parse instead returns a
frozen `PDFStructureParseFailure` with a trusted `PDFStructureFailureCode`:

```json
{
  "schemaVersion": 1,
  "status": "failure",
  "failureCode": "invalidStructure",
  "authorizesOpen": false
}
```

The only failure codes are `invalidInput` (non-byte input),
`invalidStructure` (malformed/truncated/unverifiable PDF),
`sizeLimit` (beyond the existing 16 MiB bound), `encrypted` (unsupported
encrypted PDF), and `dependencyUnavailable` (the pinned parser is missing).
The result has no fields for a filename, source path, document content,
parser exception, or untrusted PDF-controlled text. Invalid codes cannot be
used to construct a failure record, and `to_dict()` produces a fresh,
JSON-compatible dictionary. A failure **never** carries a partial
`PDFStructure`, a success value, or an authorization to launch/cache a file.

The original `parse_pdf_structure(contents)` entry point retains its
existing `PDFStructureParseError` behavior and sanitized user-facing error
messages for existing callers. The optional result-returning entry point
merely converts those known failures into bounded diagnostic categories;
it does **not** enable Enhanced protection, change scanner behavior, or
replace mandatory ClamAV verification, quarantine, and verified handoff.
