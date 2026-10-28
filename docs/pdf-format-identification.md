# Content-based PDF format identification (opener-0282)

This is the first **read-only evidence collection** step for planned Enhanced
protection. It identifies a candidate PDF's actual header **from its bytes**,
not from `.pdf`, an operating-system MIME guess, or an application association.
It does **not** activate Enhanced protection, a PDF parser or a new scanner
bypass. The deployed **Built-in** ClamAV and file-integrity gates remain
authoritative for opening files.

Use `identify_pdf_format(path)` from `pdf_format_identification.py` to
read only the first nine bytes of a local regular file. No extension check,
file copy, persistent output, document-name logging, network call or saved
preference is involved.

The immutable result is one of:

- `pdfHeader`: exact first-line `%PDF-1.0` through `%PDF-1.7`, or
  `%PDF-2.0`, terminated with CR or LF. It reports the header's declared
  version and the candidate media type `application/pdf`.
- `notPdf`: content does not begin with the required PDF signature,
  regardless of its filename or a PDF marker embedded further into another
  format. This includes a ZIP or executable renamed with a `.pdf` suffix.
- `undetermined`: truncated, malformed, unsupported-version PDF signatures,
  inaccessible/missing/changing files, symlinks, directories and special
  filesystem entries. An unknown result must never be interpreted as PDF.

The file-reading path refuses final symlinks, uses nonblocking descriptor
opening, checks that the descriptor references a regular file, and compares
filesystem identity before and after the bounded read. It returns no paths,
document bytes or exception messages. A separate byte-based function,
`identify_pdf_header(data)`, classifies caller-provided bytes without I/O.

**Security boundary:** a header match is a *candidate*, not proof of a
well-formed PDF, safe structure, lack of encryption, PDF/A/PDF/X/PDF/UA
conformance, or successful malware inspection. Its `permits_open` property
is always `False`. Future structural and feature validation must validate
whole-file contents and run required checks before treating any result as
sufficient for Enhanced protection. Leading-junk/polyglot formats are not
accepted as normal PDF headers, even if a viewer might tolerate them.

The CI suite `test-pdf-format-identification.py` tests the common reference
PDF collection with deceptive filename extensions, known header versions,
non-PDF magic bytes, embedded PDF markers, partial/malformed headers, unsafe
filesystem entries, read errors, read bounds, immutable evidence, and the
non-activation boundary.
