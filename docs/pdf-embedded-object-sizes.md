# Suspiciously large embedded PDF objects — opener-0458

`pdf_embedded_object_sizes.inspect_pdf_embedded_object_sizes(bytes)` is a
passive, optional Enhanced-only inspection stage. It examines all indexed stream
objects (including otherwise unreferenced objects) and separately follows
attachments reached through catalog and page associated files, the EmbeddedFiles
name tree and FileAttachment annotations. It also recognizes orphan streams
marked `/Type /EmbeddedFile`.

It reports aggregate counts for unusually large **encoded** PDF stream bodies
(over 1 MiB), embedded streams whose **decoded** byte count crosses 1 MiB,
compressed attachments with an expansion ratio above 100:1, and embedded file
streams whose `/Params /Size` declares over 1 MiB. The thresholds are
conservative *review indicators*, not conclusions that the object is malware.
Declared sizes are treated as untrusted hints and never used for allocations.

Only raw and single FlateDecode attachments are examined for decoded size.
Flate inflation is capped at the threshold plus one byte, so a compression
bomb is flagged without expanding its full payload. The existing strict
structure parser checks PDF header, page tree and declared stream lengths
before this inspector runs. Object streams and cross-reference streams remain
unsupported until isolation and bounded preprocessing are available, and
malformed structures or unknown attachment filters fail closed.

The immutable result contains only trusted counts. No source filenames, media
bytes, paths or scanner diagnostics are emitted and `permits_open=False`
always. Absence of oversized findings is not a clean scan verdict. The
installed Built-in ClamAV gate, signature checks, cache, quarantine,
configuration, launch handoff and user preferences are unchanged. Enhanced
is not selectable.

Resource limits: 16 MiB input via the strict parser, 4096 indexed objects,
2048 distinct indexed or referenced streams, 32 attachment specifications,
and 1 MiB plus one output byte for each compressed attachment preview. The
existing independent full attachment scan and decompression-budget checks
remain mandatory for any future enabled Enhanced stage.

CI covers small, large, compressed, unreferenced and divergent `/F`/`/UF`
embedded streams; declared-size hints; invalid PDFs and stream references;
privacy; and preservation of the installed scanner.
