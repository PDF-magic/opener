# Enhanced PDF decompression-requirement inspection (opener-0296)

The optional `pdf_decompression_requirements.py` stage inspects in-memory PDF bytes
for excessive stream decompression requirements. It is **not wired into the
installed Built-in ClamAV scanner**, does not select Enhanced or Maximum, and
never returns a PDF clean/opening verdict (`permits_open` is always false).

## Bounded algorithm

- Accept only immutable PDF bytes up to 16 MiB, with a classic cross-reference
  table, at most 1,024 pages and 8,192 indirect objects.
- Check **every indirect stream object**, including streams that are not
  reachable from any page, with a maximum of 2,048 streams.
- Count unfiltered streams without decoding. Measure single, unparameterized
  `/FlateDecode` streams with `zlib.decompressobj().decompress()` capped at
  one byte beyond the smallest applicable limit; never invoke pypdf's
  unbounded stream decoding or retain decoded content in the result.
- Enforce an 8 MiB decoded ceiling per stream, 32 MiB cumulative decoded
  output and a 200:1 maximum expansion ratio. Abort on the first excess.
- Reject malformed/truncated compressed data, trailing compressed members,
  invalid/encrypted PDFs, object or cross-reference streams, unknown filters,
  filter chains, predictors, and missing parser support rather than claiming
  complete inspection. Errors use fixed messages without untrusted file data.

The checker uses pypdf as an **optional runtime dependency**. The Linux
`scanner-tests` job executes its regression tests after installing the
existing optional pypdf 5.9.0 dependency for attachment inspection. No
scanner, browser, configuration, quarantine or signature rules are changed.

**Security boundary:** pypdf object parsing itself is not memory/time isolated.
Before any future Enhanced integration, a separate scoped task must provide a
process-isolated worker with time and memory ceilings, validate supplied file
identity, and combine this evidence with all mandatory Standard controls.
Unsupported filters are incomplete inspection, not proof of maliciousness.
Conservative refusal may include harmless PDFs with JPEG or modern PDF streams.
