# Unsupported PDF feature identification (opener-0467)

`pdf_unsupported_feature_inspection.inspect_pdf_unsupported_features(bytes)`
is a passive, bounded inventory of PDF constructs the current **structural
analyzer cannot fully inspect**. It complements, but does not replace, the
fail-closed response contract in `unsupported_pdf_features.py`.

## Feature codes

The report uses stable codes only, with no PDF-controlled strings:

- `encryptedDocument`: encryption prevents inspection without decryption.
- `crossReferenceStream` and `objectStream`: this inventory does not expand
  compressed xref/object streams.
- `unsupportedStreamFilter` and `unsupportedFilterParameters`: the bounded
  decompression inspector only supports a single `/FlateDecode` filter with
  no decode parameters; this inventory never decodes stream bytes.
- `pageContentStreams`, `annotations`, `interactiveForms`, `xfaForms`,
  `javascript`, `actions`, `externalActions`, `formActions`, and
  `unknownActionType`: the structural parser does not execute or fully
  interpret page content or action behavior.
- `embeddedFiles`, `richMedia`, and `threeDimensionalContent`: presence is
  identified without treating attachments or media payloads as inspected.
- `digitalSignatures`: signature declarations are found, not cryptographically
  verified. This includes declared certification and usage-rights structures.
- `pdfPortfolio`, `optionalContentLayers`, and `taggedStructure`: these
  document structures are identified but not semantically analyzed here.
- `incrementalRevisions`: the final trailer's `/Prev` points to an earlier
  revision; the current structural view does not validate the whole history.

A PDF may contain more than one category. Known keys and action/filter names
map only to fixed identifiers; unknown action types are reported generically.
The inspector never returns document text, scripts, paths, attachment names,
signature bytes or arbitrary PDF dictionary keys.

## Result and limits

The frozen result exposes `featureCodes`, `inspectedObjectCount`,
`inspectionComplete`, and `authorizesOpen=false`. A non-empty feature list
always has `inspectionComplete=false`; an empty list means only that this
bounded inventory found no listed feature in the traversed structural objects.
It is **not** a malware verdict, a complete PDF conformance test, or permission
to open the file. Malformed structure, missing dependencies, invalid
references, or exhausted limits raise one fixed path-free error.

The inspector caps input at the existing 16 MiB structure limit, the object
index at 4,096 objects, traversal at 65,536 nodes and 64 levels, and indirect
resolution at 32,768 steps. It refuses xref streams before constructing
`PdfReader`, does not decrypt encrypted PDFs, and never calls stream decoding.
Separate optional inspectors may cover some of these feature classes, but
they are not equivalent to a unified analyzer proving every feature was
inspected.

## Safety boundary

This is optional Enhanced-stage evidence only. It is not wired into
`scan-and-open.py`, does not activate any protection profile, and cannot
override the mandatory ClamAV scan, quarantine, signature, clean-cache, or
handoff checks. Unknown or incomplete inspection must not be interpreted as
absence or safety. The test suite covers feature markers, encrypted inputs,
xref/object streams, unknown action names, privacy, bounds and scanner
isolation.
