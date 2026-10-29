# Passive JavaScript action inspection (opener-0287)

This is a **separate, inactive Enhanced-inspection building block**, not a
JavaScript interpreter, malware verdict, replacement for ClamAV, or permission
to open a file. Standard, Enhanced and Maximum are not selectable.

`pdf_javascript_actions.inspect_pdf_javascript_actions(contents: bytes)`
reuses the **bounded strict action traversal** from opener-0286 in
`pdf_automatic_actions.py`, including:
- catalog open and additional actions,
- page, annotation, and AcroForm field additional actions,
- document-level `/Names /JavaScript` name trees,
- indirect action references and `/Next` chained actions.

Only `/S /JavaScript` actions are examined; other action kinds remain the
responsibility of the automatic-action inspector. Inert PDF `/JS` payloads
are validated as text strings, byte strings, raw streams, or bounded
single-`FlateDecode` streams. The stage **never executes JavaScript**,
evaluates links, opens documents, reads file paths, writes scripts, logs raw
PDF payloads, or returns their text.

The immutable metadata includes: JavaScript action count, total decoded script
byte count, stable hook/trigger identifiers, payload representation types,
and coarse **literal API reference hints** for network requests, file access,
and dynamic execution. These labels are *hints only*: comments, strings,
obfuscation and indirect invocation mean that both false positives and false
negatives are possible. An empty hint list **does not mean a script is safe**.

Fail-closed limits: 128 JavaScript actions, 64 KiB decoded per script and
256 KiB total, inherited 16 MiB outer PDF/1,024-page parser limits and
action-reference/depth/name-tree ceilings. Reject malformed or encrypted PDFs,
missing parser dependencies, invalid/nontext payloads, empty scripts, invalid
UTF-8/UTF-16, unsupported filters, predictors, truncated compressed streams,
expansion bombs, and graph/action failures with fixed path-free messages.
Only one bounded zlib/Flate stream is decoded; pypdf's potentially unbounded
generic `get_data` decoder is deliberately not invoked.

**Important:** The helper's `permits_open` property is always false, even
when no JavaScript is present. A future executable Enhanced policy must run
all mandatory checks and sandbox PDF parsing with wall-time and memory
limits before it can treat these findings as part of an admission decision.
The current Built-in ClamAV scanner, quarantines, 90-day clean cache,
signature checks, validated application handoff and user preferences remain
unchanged.

The `test-pdf-javascript-actions.py` CI regression covers the reference PDF
corpus, actual document/page/field/annotation hooks, indirect name-tree
chains, raw and compressed JavaScript streams, UTF-16 strings, malformed and
oversized scripts, unsupported filter failures, dependency failures,
immutability and separation from the deployed scanner.
