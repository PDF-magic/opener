# Truncated PDF security-corpus fixtures (opener-1030)

These three tracked, inert PDFs are **literal byte prefixes** of the
deterministic `clean-basic` PDF in `reference_pdf_collection.py`. No
external files, personal documents, embedded executables or malware are used.

| File | Truncation | Expected outcome |
| --- | --- | --- |
| `truncated-stream.pdf` | Halfway through the page-content stream | Structural integrity cannot be verified |
| `truncated-xref.pdf` | Midway through the first in-use cross-reference offset | Structural integrity cannot be verified |
| `truncated-eof.pdf` | Three bytes into the terminal `%%EOF` marker | Structural integrity cannot be verified |

The last case intentionally exercises parsers that can recover a document
despite a missing complete EOF marker. The optional strict integrity checks
must still fail closed. These fixtures are test inputs, **not** any scanner
verdict, authorization to open a PDF, or activation of Enhanced/Maximum.

Run `PYTHONPATH=. python3 tests/security/truncated-pdfs.py -v` from the
repository root. CI runs this check within the existing `scanner-tests` job.
