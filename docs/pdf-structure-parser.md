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
