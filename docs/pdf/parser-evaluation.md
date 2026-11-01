# PDF parsing foundation: library selection (opener-0406)

**Decision: retain pypdf, update reviewed pin to 6.21.4.** The parser was introduced by [PR #179](https://github.com/PDF-magic/opener/pull/179)
for optional, strict Enhanced PDF structure inspection. The dependency is
**exactly pinned** as `pypdf==6.21.4` in `requirements-enhanced-pdf.txt`.
This decision confirms that selection; it neither adds a competing parser
nor enables the planned Enhanced profile.

## Evaluation criteria and candidates

Compared on 2026-10-29 against public upstream documentation. "PDF 2.0"
means relevant PDF 2.0 syntax is understood, **not** that every feature
defined by ISO 32000-2 is implemented. A parser accepting a file is not a
malware verdict.

| Maintained library | PDF version / feature coverage | Malformed-document behavior | Large-document memory tradeoff | License and package impact |
| --- | --- | --- | --- | --- |
| **pypdf 6.21.4 (selected)** | Reads traditional PDF 1.x structures and many PDF 2.0 constructs; PDF 2.0 feature coverage is incomplete. Supports object streams; not every optional-content or incremental-update feature is fully handled. The application's *current* header validator admits only PDF 1.0–1.7 and 2.0. | `PdfReader(..., strict=True)` raises on many syntax violations; permissive `strict=False` can recover with warnings, but is **not used** for the security-relevant structure stage. Strict mode is not proof that every inconsistency is detected. | Pure Python: Python object graphs and input `BytesIO` can increase peak RSS with object/page count. Input size is limited to 16 MiB and page count to 1,024, but these **do not bound adversarial heap or CPU consumption**. | BSD-3-Clause; pure-Python distribution, no extra required binary PDF runtime for current parsing. Optional extras are not installed by the pin. |
| **pikepdf (QPDF)** | QPDF-based PDF 1.x and 2.0 structural processing; feature-specific verification still necessary. Strong low-level object and stream manipulation. | Automatically repairs many kinds of PDF damage on open, which can conceal original anomalies unless the workflow separately detects and rejects repair. | Native QPDF allocations reduce Python object overhead in some workflows but retain native buffers and can allocate heavily during repair or decoding. Do not infer a universal RSS advantage. | MPL-2.0 for pikepdf plus Apache-2.0 QPDF and other bundled binary dependencies, varying by wheel/platform; license notices and native packaging required. |
| **PyMuPDF (MuPDF)** | Handles PDF 1.x and 2.0 documents along with other formats; rendering capabilities exceed this metadata-only stage, and feature-specific compatibility still needs tests. | MuPDF can repair invalid cross-reference data; `Document.is_repaired` identifies some repaired files. This recovery requires explicit rejection if used for an admission check. | Native engine plus optional rendering/decompression caches; can be efficient for targeted page reads but rendering/extraction can consume far more RAM. No rendering is needed for the selected stage. | AGPL-3.0 or paid commercial license, with bundled native engine and extra compatibility review; this AGPL project's license alone is not a substitute for review of combined distribution obligations. |

Evidence: [pypdf version support](https://pypdf.readthedocs.io/en/latest/user/pdf-version-support.html),
[pypdf strictness](https://pypdf.readthedocs.io/en/latest/user/robustness.html),
[pypdf license](https://github.com/py-pdf/pypdf/blob/main/pyproject.toml),
[pikepdf design and license](https://github.com/pikepdf/pikepdf),
[pikepdf bundled dependency licenses](https://github.com/pikepdf/pikepdf/blob/main/third-party-licenses/README.md),
[PyMuPDF damaged-file recovery](https://pymupdf.readthedocs.io/en/latest/app3.html),
and [PyMuPDF licensing](https://pymupdf.io/licensing).
Version/feature claims are upstream capabilities, not a certification
that **this application's** restricted inspection admits all those inputs.

## Large-document memory comparison: measurement protocol

The qualitative differences above describe allocation models, **not**
benchmarked rankings. Peak RSS must be measured on the **same** host, OS,
Python version, fixture, and installed library versions. The offline
`pdf_parser_memory_benchmark.py` generates a deterministic synthetic PDF
with a bounded page tree and one shared, uncompressed payload stream.
Each candidate is parsed in a **fresh subprocess**; it reports the child
process's `ru_maxrss` (MiB), Python package version, page count and input
bytes. Imports, source bytes, PDF objects and native allocations count toward
peak RSS. No user documents, filesystem PDF reads, HTTP calls, or executable
PDF content are involved.

Run after installing the optional candidates **in a disposable environment**
and independently checking their licenses:

```sh
python3 -m pip install -r requirements-enhanced-pdf.txt
python3 pdf_parser_memory_benchmark.py --parser pypdf --pages 512 --stream-bytes 4194304
# Optionally, in an isolated evaluation environment with pikepdf and PyMuPDF:
python3 pdf_parser_memory_benchmark.py --parser all --pages 512 --stream-bytes 4194304
```

Missing optional candidates are reported as `not-installed`. This is a
*structural baseline*, not a decompression bomb, malware test, real-world
performance claim, or stable acceptance threshold. Variations in package
version, wheel architecture, Python allocator and page/stream pattern
affect the results. To test larger content independently, vary page count
(up to 1,024) and shared stream size (up to 8 MiB) without bypassing the
application's separate 16 MiB structure input limit. Future integration
must also run untrusted parsing under process memory/time budgets, not
rely on benchmarks or byte-count limits alone.

## Selection and release pin

pypdf is the smallest change for the existing pure-Python structural
inspection, offers strictness controls, and minimizes binary packaging and
additional license surface. Its 6.21.4 release (2026-10-28) fixes three reported denial-of-service
advisories (CVE-2026-119203, CVE-2026-119204, CVE-2026-119205),
and retains earlier cross-reference entry limits:
[release notes](https://pypdf.readthedocs.io/en/6.21.4/meta/CHANGELOG.html),
[PyPI release with provenance](https://pypi.org/project/pypdf/6.21.4/).
Earlier pypdf releases have documented memory-exhaustion advisories, including
[CVE-2026-31826](https://github.com/py-pdf/pypdf/security/advisories/GHSA-hqmh-ppp3-xvm7)
(fixed in 6.8.0); selecting a newer pin does **not** eliminate the need
for input limits and isolation.

The CI runner installs this same exact pin for **all** optional PDF
inspection tests (it must not silently downgrade to pypdf 5.9.0).
The selection regression validates package metadata, pinned version,
strict parsing, fixture-level memory measurement, fail-closed bounds,
and unchanged Built-in scanner integration. Updating the version later
requires security review and corresponding regression updates; no
floating requirement or automatic dependency upgrade is authorized.

**Non-goals:** enable Enhanced/Maximum, change scanner policy, parse real
user documents during a benchmark, add a second dependency in production,
or modify user settings and preferences.
