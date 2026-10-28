# Enhanced PDF embedded-file inspection (opener-0285)

`enhanced_embedded_files.py` provides an **independent, fail-closed inspection
stage**, not an alternate PDF opener. It enumerates embedded file specifications
in the catalog's EmbeddedFiles name tree, document/page associated-file arrays,
and page FileAttachment annotations. Each discovered embedded stream is decoded
(with only raw or bounded FlateDecode streams supported) and its bytes are passed
directly to ClamAV through stdin, without writing extracted attachments to disk.

The inspector requires `pypdf==5.9.0` when invoked. Missing dependencies,
encrypted/malformed PDFs, unrecognized attachment filters, oversize documents or
payloads, and scanner failures/warnings block the stage. Attachment filenames
are never sent to ClamAV or included in errors. The return value only reports
how many attachments were inspected and their total byte count; it **never**
declares the outer PDF clean, clears quarantine, writes a clean cache, or
launches an application.

For example, a future Enhanced pipeline can call
`inspect_embedded_files(pdf_path, verified_clamscan, verified_signature_dir)`
**in addition to** the existing Standard scan, database-freshness, integrity,
and verified-handoff gates. The installed Built-in scanner is unchanged,
and Enhanced remains **non-selectable**. Integration and sandboxing of this
third-party PDF parser, plus further PDF structural controls, need independent
security review and tests before a real Enhanced profile can be enabled.

Limits: 64 MiB outer PDF, 16 MiB per embedded stream, 64 MiB total decoded
attachments, at most 32 attachments, 1,024 pages, 256 name-tree nodes, and
120 seconds per embedded ClamAV invocation. Exceeding limits fails closed.
These intentionally conservative limits affect only this inactive stage,
**not** the existing unlimited-configured-size Built-in PDF scanner.
