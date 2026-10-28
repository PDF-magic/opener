# Process-isolated complex PDF inspection (opener-0306)

`maximum_isolated_analysis.run_isolated_pdf_analysis(contents, inspection)`
runs one **fixed, trusted passive PDF inspector** inside a separate Python
interpreter, communicating solely through stdin PDF bytes and a small,
validated JSON response. The returned frozen result is **evidence only**:
`permits_open` is always false, and no clean or launch verdict exists.

The currently approved dispatch choices are `structureAmbiguity`,
`malformedStructures`, and `decompressionRequirements`. They reuse the
existing strict PDF inspections rather than duplicating their parsing logic.
The caller cannot supply an executable, arbitrary module, script, document
path, command-line flag, or PDF-originated inspector name.

The parent accepts immutable bytes up to **16 MiB**; invalid input fails
before worker launch. The child is created with Python `-I -B`, a fixed
minimal environment, no shell, no inherited extra file descriptors, a new
process session and a fixed working directory. Before loading any PDF parser
it applies POSIX ceilings of **25 CPU seconds**, **1 GiB virtual memory**,
zero core dumps and zero output-file size; the parent enforces a
**30-second wall-clock timeout**. The worker needs no PDF filesystem path,
does not save a PDF, and returns only fixed numeric fields plus its PID.
Invalid reports, premature termination, parser errors, unsupported features,
unavailable resources, timeouts and malformed/oversized responses all produce
the same fixed path-free block error. The parent rejects duplicate JSON keys,
extra keys, nonintegers and any child claim that opening is permitted.

This implements **process and resource isolation**, *not* a full OS sandbox.
It does not provide a claim that the child has no network access, nor does it
replace future OS-specific sandboxing or a complete Maximum analysis engine.
It does not execute JavaScript, submit forms or follow PDF links. The worker
does not run the deployed ClamAV scanner or replace any required controls.
Additional inspection stages, verified file identity, trustworthy sandbox
controls, full admission policy and Maximum activation remain separate work.
The current Built-in ClamAV scan path, quarantine, clean cache, browser
settings, and user customizations remain unchanged.

`test-maximum-isolated-analysis.py` exercises the *real subprocess* with
generated PDF fixtures, separate process IDs, all approved dispatches,
malformed input, crash/timeout simulation, invalid output, fixed error
messages, immutable reports and installed scanner isolation on both Linux
and macOS CI. The optional parser dependency is pinned to `pypdf==5.9.0`.
