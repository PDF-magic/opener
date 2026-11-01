# Many embedded PDF objects benchmark (opener-1077)

This opt-in benchmark times the **existing passive Enhanced**
`pdf_embedded_object_sizes.inspect_pdf_embedded_object_sizes` inspector on one
bounded, deterministic PDF generated solely in memory. It contains one page
that references **256 genuine 1×1 image XObjects** and **24 harmless embedded
file streams** through the PDF name tree (281 streams total, including page
content). These are actual indirect stream objects, not repeated text tokens or
unreachable fake objects. The fixture is under the 16 MiB structural parser
input limit, the 4,096-object inspection limit, and the 32-attachment ceiling.
No fetched or private PDF is ever processed.

From the repository root with `requirements-enhanced-pdf.txt` installed:

```sh
PYTHONPATH=. python3 many_embedded_objects_benchmark.py --samples 5
```

The script creates the exact same bytes before timing and performs one
**discarded warmup** followed by 3–10 inspections. It verifies each result
really enumerated all **281** streams and **24** embedded files, with no large
object flags. The JSON reports the median and nearest-rank p90 **milliseconds
for inspection calls only**. An exception, failed/incomplete result, nonpositive
timing, or unexpected stream count produces no results. Fixture construction,
PDF rendering, antivirus scanning, quarantine checks, browser handoff, and
end-to-end opening are **not** measured. The benchmark never infers a clean
malware verdict or permission to open from passive inspection.

CI runs a three-sample real inspection as a **smoke benchmark** on its runner,
plus deterministic test checks. CI timing is workload evidence, not a guaranteed
latency budget, speed-up, or representative macOS/ClamAV baseline. For useful
comparisons, record the CPU, Python and pinned `pypdf` versions and repeat on
controlled machines. The script does not alter scanner parameters, signature
freshness, clean-cache logic, selected PDF destinations, or saved user settings.
