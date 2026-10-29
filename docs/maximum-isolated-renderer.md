# Maximum isolated PDF page rendering (opener-0314)

The planned Maximum tier can use
`maximum_isolated_renderer.render_isolated_pdf_page(pdf_bytes, page_index)`
and `render_isolated_pdf_pages(pdf_bytes, (0, 1))` to produce PNG pages
inside **separate, bounded worker processes**. The active ClamAV scanner,
browser handoff, PDF preview, user customizations and non-selectable Maximum
profile remain unchanged.

**Rendering is not approval.** The result is immutable and always has
`permits_open=False`. The existing mandatory scanner, quarantine, verified
file identity, required Enhanced checks and final admission policy must be
satisfied separately. No document is automatically opened or handed off
because a page was rasterized.

The parent accepts at most **8 MiB** of immutable PDF bytes and a validated
zero-based page index. Up to **four distinct pages** may be requested per
batch; each runs in its own child process. The child receives only PDF bytes
via standard input; no PDF path or script text is placed on its command
line. The sole approved renderer is a pinned PyMuPDF/MuPDF build in the
isolated process. Embedded JavaScript, automatic actions, forms and URLs
are never intentionally executed or followed. Annotation painting is
disabled.

The worker reuses the trusted Maximum isolated-analysis
`_apply_limits()` entry point **before importing PyMuPDF**. That applies
the existing CPU, memory, no-core and no-output-file limits. The macOS
resident-memory watchdog stays armed during the complete render and is
explicitly disarmed before interpreter shutdown, avoiding a late `SIGALRM`
after valid PNG delivery.

On macOS, the renderer is launched through `/usr/bin/sandbox-exec` with a
deny-by-default Seatbelt profile. File contents are readable only from the
trusted renderer source directory, the selected Python runtime prefixes and
required operating-system runtime locations. The policy grants no filesystem
writes, and it does not permit reading arbitrary user documents, home
directories or temporary files. The child receives only PDF bytes through
stdin; it gets no PDF pathname, a minimal environment, closed inherited file
descriptors, a new process session and a 30-second deadline. If the platform,
sandbox executable or runtime paths cannot be validated, rendering fails
closed rather than falling back to an unsandboxed child. Filesystem metadata
checks are allowed for path resolution, but do not grant broad file-content
access. This renderer boundary is separate from network and admission-policy
controls, and does not enable the planned Maximum tier.

Documents with more than 512 pages, password-protected PDFs, invalid
pages or malformed data fail closed. The renderer rejects absurd page
geometry and calculates a scale **before** rasterization so each bitmap
is at most 1024 pixels per side and at most 1,048,576 pixels in total.
Each rendered PNG is capped at **4 MiB**; a fixed-size binary header,
bounded JSON numeric metadata and strict PNG dimension validation prevent
unexpected or forged worker output being accepted. No filesystem output
is created, and images are returned in-memory only. Errors produce a
single fixed, path-free exception and cannot expose PDF-controlled
filenames, extracted text, raw renderer diagnostics or an opening verdict.

`test-maximum-isolated-renderer.py` renders synthetic two-page PDFs in
real isolated workers on **macOS**, and verifies fail-closed refusal without
Seatbelt on Linux. It tests per-page image differences, scaling, bounded
batches, encrypted/invalid inputs, worker failures, protocol tampering,
immutability and noninterference with the deployed scanner. The dedicated
`.github/workflows/maximum-isolated-renderer.yml` workflow installs
`pymupdf==1.26.7` and runs the regression suite on Linux and macOS. The
macOS job performs actual kernel-enforced private-file read/write denial
probes and real rasterization; the Linux job verifies that rendering refuses
to run without the required filesystem sandbox. Existing CI workflows and
user preferences are preserved.
