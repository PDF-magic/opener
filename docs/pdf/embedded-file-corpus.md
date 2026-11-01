# Embedded-file PDF security corpus — opener-1038

The embedded_file_corpus.py module generates four small, deterministic, inert
PDF **documents** in memory, each containing real /EmbeddedFile streams and
/Filespec objects. The cases cover:

- **name-tree-multiple**: two text attachments in catalog /Names /EmbeddedFiles.
- **catalog-associated-only**: catalog /AF without an embedded-files name tree.
- **page-associated-only**: page /AF without a name tree.
- **annotation-only**: a page /FileAttachment annotation referencing /FS.

The fixtures contain plain text/CSV only, with no executable payloads,
JavaScript, URLs, launch actions, or actual malware. Attachment names are
not trusted as evidence of file type or scan safety. The corpus remains
separate from the six stable clean REFERENCE_PDFS profile baselines.

The tests/pdf/embedded-file-corpus.py suite checks strict PDF decoding,
reproducible bytes, each carrier's real file specifications and payloads,
passive type inspection, mocked per-attachment ClamAV stdin scans and
fail-closed rejection. No subprocess or network access occurs in the test.
A successful attachment-inspection result never authorizes opening the outer
PDF: the existing scanner, quarantine, cache, profiles and user choices
remain intact.

Run from the repository root after installing pypdf==5.9.0:

    PYTHONPATH=. python3 tests/pdf/embedded-file-corpus.py -v
