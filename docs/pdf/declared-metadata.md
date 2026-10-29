# Passive extraction of declared PDF document metadata (opener-0453)

`pdf_declared_metadata.extract_pdf_declared_metadata(contents: bytes)`
is an opt-in, read-only Enhanced inspection primitive operating on immutable
PDF bytes. It first runs the existing strict, bounded PDF structure parser.

## Supported declarations

- PDF trailer `/Info` dictionary, including standard fields `/Title`,
  `/Author`, `/Subject`, `/Keywords`, `/Creator`, `/Producer`,
  `/CreationDate`, `/ModDate` and `/Trapped`. It resolves direct and
  bounded indirect values, and rejects malformed supported fields.
- Catalog `/Metadata` stream with `/Type /Metadata` and
  `/Subtype /XML`. It accepts raw XML or a single bounded
  `/FlateDecode` encoding, extracts selected Dublin Core and Adobe
  PDF/XMP properties, including title, author/creator, description,
  keywords, producer and creation/modification dates.
- Information dictionary values and XMP properties are **reported
  separately**. A disagreement is retained rather than silently treating
  either declaration as authoritative. Trust assessment and consistency
  checks are separate future work.

A frozen `PDFDeclaredMetadata` result contains sorted, fixed-name field
pairs and a boolean XMP presence indicator. `to_dict()` creates a
detached JSON-compatible result with `authorizesOpen: false`. Normal
`repr()` intentionally omits the user-controlled metadata values.

**Privacy warning:** PDF titles, authors, producer names, keywords, and XMP
fields can contain private information or malicious text. The values are
extracted only in memory and are not logged, cached, sent over a network, or
automatically displayed. Any caller that opts into `to_dict()` must
separately handle or redact the extracted strings. They are untrusted
declarations, never verified identities, file origins or safety evidence.

## Limits and failures

- 16 MiB PDF input and the shared strict parser's page/structure limits.
- 1,024 characters per extracted text field, fixed field-name allowlist
  and a cap of 32 indirect-reference hops.
- Up to 128 KiB compressed XMP input and decoded XML, 1,024 XML nodes,
  32 XML nesting levels, and eight creators/items per field.
- XML DTDs/entity declarations are refused. Unknown XML properties and
  unknown `/Info` dictionary keys are not turned into arbitrary result
  names. Unsupported compression, malformed metadata entries, encryption,
  parser failures, or limits produce the same fixed, path-free,
  `PDFDeclaredMetadataError` rather than a partial or false-empty result.
- The metadata stream is never executed, launched, opened as a file, or
  evaluated as script. XMP parsing does not fetch external entities.

This stage does not enable Enhanced, make a malware verdict, authorize a
clean cache or bypass the installed ClamAV scan, quarantine handling or
browser handoff. User settings and other checklist tasks remain unchanged.
CI builds harmless real PDF fixtures to test Info/XMP extraction, encoding,
privacy, malformed/oversized inputs and safety isolation.
