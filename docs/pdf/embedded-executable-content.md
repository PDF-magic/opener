# Passive embedded executable-content inspection (opener-0295)

`pdf_embedded_executable_content.inspect_pdf_embedded_executable_content(pdf_bytes)`
checks the **bytes** of indexed PDF stream objects under strict `pypdf` parsing,
including streams not reachable through the catalog or listed as attachments.
It recognizes PE/DOS MZ, ELF, Mach-O, ambiguous Mach-O fat/Java class,
WebAssembly and shebang-script signatures. A filename or extension is never
accepted as proof of executable content. The immutable result reports only
stream and finding counts plus fixed categories, never payloads or file paths;
`permits_open` is always false, even when no signature is found.

The stage accepts immutable in-memory PDF bytes. It bounds documents to 16 MiB,
1,024 pages and 4,096 indexed objects; examines at most 1,024 streams, with
4 MiB per stream and 16 MiB total decoded stream data. Raw and single
`FlateDecode` streams are supported using bounded decompression, and malformed,
encrypted, oversized or unsupported streams fail closed. It does not execute,
extract to disk, launch, or network-fetch any embedded content.

These signatures do **not** detect every possible executable, script, archive
payload or obfuscated program. ZIP/JAR payload inspection, action-dictionary
JavaScript inspection and ClamAV attachment scanning are separate stages:
[embedded attachment inspection](../enhanced/embedded-file-inspection.md),
[external launch action inspection](external-launch-actions.md), and the
concurrent JavaScript-action inspector PR #184. A signature-free result cannot
allow opening or replace the installed ClamAV gate. This future Enhanced stage
requires an isolated time/memory-bounded worker and an independently reviewed
integration before enabling Enhanced. Built-in scanning, quarantine, caching,
signature freshness, browser handoff and saved user preferences are unchanged.
