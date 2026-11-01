# Limitations of PDF structural analysis (opener-1116)

PDF structural analysis is **evidence about PDF formatting and selected objects**,
not an antivirus scan, a proof that a document is safe, or permission to open it.
The optional `pdf_structure_parser.parse_pdf_structure(bytes)` helper uses
strict, pinned pypdf parsing to validate a supported PDF header, cross-reference
data, indexed stream lengths, and a bounded page tree. A successful result
reports only `pdfVersion` and `pageCount` and has
`authorizesOpen: false`.

## What structural success does not establish

- **Malware and actual behavior:** It does not detect all malware, render pages,
  evaluate JavaScript, trigger actions, follow URLs, make network requests,
  open embedded files, or prove that a PDF viewer will handle the file safely.
  Some separate optional inspectors identify suspicious actions or links, but
  identifying them is not equivalent to executing or fully analyzing them.
- **Features and hidden content:** It does not comprehensively inspect page
  content streams, annotations, AcroForms/XFA, attachments, rich media, 3D
  content, optional layers, portfolios, tagged structures, or every PDF 2.0
  feature. A declared digital signature is **not cryptographically verified**
  by structural parsing. Unknown or unsupported filters and features cannot
  be treated as absent or harmless.
- **Revision history and parser differences:** Strict parsing of the final
  cross-reference view does not independently validate every earlier
  incremental revision or all unreachable historical objects. The base
  parser can resolve cross-reference streams and object streams, but the
  separate unsupported-feature inventory deliberately does not expand them.
  Other specialized inspectors have narrower, independently documented
  coverage; passing one does not imply that the others ran.
- **Encrypted or unusual documents:** The helper refuses encrypted PDFs,
  including password-protected files, rather than decrypting them. A
  legitimate PDF can also be rejected because its version, size, format,
  structures or resources exceed supported limits. Rejection is **not**
  evidence that malware was found; successful parsing is **not** evidence
  that malware is absent.

## Boundaries and incomplete inspection

The current strict parser limits input to **16 MiB input**, **4,096 indexed indirect objects**, **1,024 pages**, and **64 nested structure levels**.
Its decoded-stream budgets are **8 MiB per indexed stream** and **32 MiB
cumulative**. These are admission and decoding limits, not a guarantee
against CPU exhaustion, memory pressure, or parser vulnerabilities.

Direct in-process `parse_pdf_structure(bytes)` has **no execution deadline or
process sandbox**. The separate opt-in
`timed_pdf_structure_analysis.parse_pdf_structure_timed(bytes)` runs in a
supervised worker with a deadline and OS-specific filesystem confinement;
that wrapper does not turn structural parsing into a complete malware scan
or prove every system resource is isolated.

Malformed, encrypted, oversized, unsupported, ambiguous, unavailable-parser,
or otherwise uninspectable cases must be handled as **incomplete/blocked**
inspection, not a clean result. The parser returns a fixed, path-free
failure instead of PDF-controlled text or partial opening authorization.
The separate unsupported-feature inventory can identify known markers, but
an empty feature list only means none of those markers were found within
its bounded scope.

## Current protection and safe interpretation

**Only the installed Built-in ClamAV scan gate is active.** Standard,
Enhanced, and Maximum are not selectable; optional PDF structural analysis
is **not active** in the installed scan-and-open path. It cannot replace
ClamAV detection and signature freshness, file-integrity verification,
quarantine handling, cache rules, or verified handoff to the user's selected
PDF application. Even if a future Enhanced analysis succeeds, the mandatory
scanner checks still decide whether opening is permitted. Failure or
incomplete inspection must not be interpreted as safe or silently bypassed.

See [the strict parser and its result contract](structure-parser.md),
[feature-inventory blind spots](unsupported-feature-inspection.md),
[incremental revision coverage](incremental-revisions.md),
[the parser selection and tradeoffs](parser-evaluation.md), and
[the unsupported-feature fail-closed response](../unsupported-pdf-features.md).
