# Explicit PDF download maximum-size limit (opener-0770)

The size-limited transfer primitive in `explicit-pdf-download-size.js`
provides a fixed **100 MiB maximum** for a selected PDF obtained by a
separately trusted streaming transport. A caller can choose a smaller
positive integer `maxBytes`, but cannot disable or increase the cap.
Individual chunks are limited to 8 MiB.

`copyExplicitPdfWithinSizeLimit({ source, destination, maxBytes })`
takes an async iterable of `Uint8Array` chunks and a trusted
**private, atomic/quarantined** destination with async `write(chunk)`,
`commit(bytes)` and `abort()` methods. It validates the exact received
byte count BEFORE forwarding each chunk. If a chunk would exceed the cap,
it is never passed to `write`. The source is closed and the partial
destination is aborted. Invalid chunks, empty transfers, missing or
invalid methods, and stream/sink failures also abort without committing.
Success is possible only after EOF, a nonempty stream, and a positive
destination commit acknowledgment; the result is frozen and still has
`scanVerified:false`, `authorizesScan:false`, and
`authorizesOpen:false`.

This checks **actual streamed bytes**, not an attacker-controlled HTTP
`Content-Length` or browser `totalBytes` declaration. It also handles
sources with unknown lengths and enforces the exact inclusive boundary.
It does not buffer entire PDFs or expose private URLs/paths in results.

**Integration prerequisite:** the shipped shared WebExtension background
is intentionally inert. The existing `downloads.download()` mechanism
(opener-0764) has no browser-level hard maximum-size option, and it is
NOT automatically routed through this streaming primitive. Therefore,
merely using `downloads.download()` or cancelling it based on a later
reported size **cannot guarantee** a download-time 100 MiB cap. Before
enabling explicit Scan This PDF acquisition, a separately reviewed trusted
browser/native streaming transport and atomic destination must use the
byte-counted limiter *before writing*, and independently enforce browser
auto-open prevention and native file identity/stability checks.

This is a maximum for the explicit PDF acquisition route only; it does
not change ClamAV's existing PDF scan size arguments, scanner signature
freshness, quarantine, native scan-before-open rules, saved preferences or
other downloads. No network, file or browser operations occur on import.
The Node regression suite covers exact boundaries, overflow, early
iterator closure, malformed chunks, failure cleanup, immutable non-opening
results and no extension privilege changes; `npm test` includes it and
`scanner-tests` CI executes it explicitly.
