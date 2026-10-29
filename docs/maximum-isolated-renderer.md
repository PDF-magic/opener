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
the existing CPU, memory, no-core and no-output-file limits. The macOS resident-memory watchdog stays armed during the complete render
and is explicitly disarmed before interpreter shutdown, avoiding a late
`SIGALRM` after valid PNG delivery. Parent-side
process isolation also uses Python `-I -B`, no shell, a minimal environment,
closed inherited file descriptors, a new process session, 30-second
deadline, private stdin and discarded stderr. Network isolation is enforced
before the renderer processes PDF bytes: macOS launches the child under the
fixed `/usr/bin/sandbox-exec` Seatbelt profile `(deny network*)`; Linux
installs a libseccomp filter before reading the PDF or importing PyMuPDF.
That filter denies socket creation and socket operations including connect,
bind and listen, as well as available io_uring entry points. If the required
mechanism cannot be applied, rendering fails closed without an unsandboxed
retry. A dedicated filesystem sandbox remains a separate prerequisite before
enabling the Maximum tier in production.

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
real isolated workers on **Linux and macOS**, tests per-page image
differences, scaling, bounded batches, encrypted/invalid inputs,
worker failures, protocol tampering, immutability and noninterference
with the deployed scanner. The dedicated
`.github/workflows/maximum-isolated-renderer.yml` workflow installs
`pymupdf==2.0` and runs the regression suite in both operating systems.
Existing CI workflows and user preferences are preserved.
