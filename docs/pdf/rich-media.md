# Passive PDF rich-media content detection (opener-0447)

The optional `pdf_rich_media.inspect_pdf_rich_media(bytes)` stage identifies
rich-media content beyond the existing `/Subtype /RichMedia` annotation
category, which is already recognized by `pdf_annotations.py` (merged PR
#191). It looks for referenced or indexed orphan `/RichMediaContent`
dictionaries, `/RichMediaConfiguration` objects, and media asset name-tree
file specifications. It also recognizes `/RichMediaSettings` dictionaries,
but does **not** trigger activation, play content, open files, resolve URLs,
decode streams or run scripts.

The return value is a frozen, bounded count of rich-media annotations, content
dictionaries, configurations and asset references. It contains no media bytes,
filenames, URLs or application targets and always has `permits_open=False`.
Malformed references, inconsistent structures, unsupported compressed object
streams, encrypted PDFs and resource-limit breaches fail closed with a fixed,
path-free error. An absence of findings is not a malware verdict.

Limits: 16 MiB PDF input, 1,024 pages, 4,096 indexed objects, 65,536
traversal nodes, 256 media asset tree nodes and 512 counted media entries per
category. Asset filespecs are **identified but not opened or scanned** by this
detection stage; existing separate embedded-file inspection remains responsible
for decoding and ClamAV verification of actual attachment bytes.

CI runs `test-pdf-rich-media.py` using the repository's pinned optional
pypdf dependency. Fixtures cover annotation-bound and orphan content,
configuration and asset references, malformed content and name trees,
safety isolation, absence of network/process execution and data confidentiality.
The installed Built-in ClamAV scan gate, cache, quarantine handling, settings,
and application handoff are unchanged; Enhanced remains non-selectable.
