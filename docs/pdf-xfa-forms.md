# Passive XFA form detection (opener-0445)

The optional Enhanced building block `pdf_xfa_forms.inspect_pdf_xfa_forms(contents)`
detects whether a structurally valid PDF contains **XML Forms Architecture
(XFA)** form data at the document catalog's `/AcroForm /XFA` entry.

The XFA entry is recognized in both standard representations:

- A single, possibly indirect, PDF stream object.
- An array alternating nonempty PDF packet-name strings and stream objects,
  including indirect references to the array and individual streams.

The frozen `PDFXFAInspection` result records only a fixed representation
(`none`, `stream`, or `packets`), the number of named packet pairs
when enumerated, and a derived `contains_xfa` property. `to_dict()`
produces a detached JSON-compatible record with
`authorizesOpen: false`. Neither XML contents, stream bytes, packet
names, filenames, paths, parser errors, nor document-provided strings are
returned. The inspector does **not** decode, parse, execute, or validate
the underlying XML or any embedded scripts.

A valid PDF with no `/XFA` entry reports `none`, including ordinary
AcroForms with only `/Fields`. Malformed, unsupported, or unresolved
XFA representations and parser failures raise a fixed, content-free
`PDFXFAInspectionError` rather than falsely reporting no XFA. A packet
array contains 1–64 pairs, with bounded names and indirect-reference
resolution. The existing strict PDF structure parser still enforces its
input, page, and stream-related limits before this check.

This is **detection of XFA presence, not safe XML interpretation** and not a
complete assessment of arbitrary orphaned XFA-like objects. A document
without recognized XFA may still contain other dangerous behavior. No result
is a malware verdict or grants permission to open or cache a file.

The installed Built-in ClamAV scanner, quarantine checks, verified browser
handoff, protection profile selection, and saved preferences remain unchanged.
The optional Enhanced stage requires its independently planned isolation and
policy integration before it can be used as an enforced protection gate.
