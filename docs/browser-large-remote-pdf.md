# Large remote PDF browser verification (opener-0809)

The existing **Chrome package smoke test** and **Firefox built-in PDF viewer
smoke test** now load a generated **16 MiB+ valid PDF** from a controlled
`127.0.0.1` HTTP endpoint, in addition to their existing small PDF and
authenticated-endpoint cases. These tests exercise an actual browser network
navigation and built-in PDF viewer, not a mocked response or URL suffix.

The PDF contains one text page with a deliberately large, inert whitespace
region **inside its declared uncompressed PDF content stream**. The fixture
builds valid object offsets and a cross-reference table. Its bytes are
generated in memory; no binary fixture, user PDF, external URL or credentials
are read.

The HTTP server supports `GET`, `HEAD`, full (`200`) and single-byte-range
(`206`) responses, including open-ended and suffix ranges. It advertises
`Accept-Ranges: bytes`, declares exact body lengths and `Content-Range`,
sends data through bounded 64 KiB chunks with Node stream backpressure,
and refuses unsatisfiable/malformed/multipart ranges with `416`. The browser
may choose full or partial retrieval, so the tests do not assume a particular
browser-specific transfer strategy.

The real-browser assertions require a nonempty HTTP request count and
actual **Chrome built-in PDF viewer evidence** (PDF extension target/frame or
embedded PDF plugin), or **Firefox PDF.js initialized with one document page
and rendered first-page content**. A successful HTTP status alone cannot
pass either viewer test. The independent Node tests validate the entire PDF
body, response length and content type, exact initial/suffix/open-ended range
bytes, rejection of invalid ranges, and CI wiring.

Implementation and coverage:
- [Large PDF HTTP fixture](../extensions/webextension/scripts/large-remote-pdf-fixture.mjs)
- [Fixture and CI regression tests](../extensions/webextension/tests/large-remote-pdf.test.mjs)
- [Chrome viewer smoke](../extensions/webextension/scripts/test-chrome-pdf-viewer.mjs)
- [Firefox PDF.js smoke](../extensions/webextension/scripts/test-firefox-pdf-viewer.mjs)

This is a deterministic, locally hosted **simulation of a remote HTTP PDF**
rather than a measurement of a third-party server, proxy, WAN latency, TLS
certificates, CDN cache, or production authentication. It tests that the
browsers can open a large PDF over HTTP; it **does not prove** that PDF Magic
Opener can intercept browser PDF rendering, acquire a remote document for
scanning, or open unscanned PDFs. The extension's optional interception
remains disabled. Separately, the existing [explicit PDF download size
policy](../extensions/webextension/src/explicit-pdf-download-size.md)
continues to impose its 100 MiB cap on the *unconnected, trusted-streaming
primitive*; this test does not modify or bypass that limit.

No native scanner, quarantine, browser permissions, installed profiles,
user preferences or selected PDF app are changed. The disposable browser
profiles and loopback server are closed by the existing smoke harnesses.
