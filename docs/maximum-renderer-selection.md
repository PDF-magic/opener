# Maximum PDF rendering engine selection (opener-0483)

Review date: 2026-10-29.

## Decision

Use **PyMuPDF 2.0** (the `pymupdf` distribution, embedding **MuPDF 1.28.5**) as the
raster renderer for the planned Maximum sanitization pipeline. Pin the exact release
in `.github/workflows/maximum-isolated-renderer.yml`; do not use a floating version. The dedicated CI installs the exact renderer wheel with `--no-deps`: this worker calls the native rendering API only and does not use the additional layout/LLM packages, avoiding unnecessary runtime surface and memory pressure under the worker's fixed limits.
PyMuPDF is already integrated behind `maximum_render_worker.py`, supports actual PDF
page-to-PNG rendering on Linux and macOS, and is maintained by Artifex. The upstream
2.0 release is dated 2026-10-19 and states that existing rendering APIs continue to
work. The separate `pypdf` dependency remains the structural parser, not the rasterizer.

Sources: [upstream 2.0 release](https://github.com/pymupdf/PyMuPDF/releases/tag/2.0),
[official changelog](https://pymupdf.io/changelog), and
[PyPI release metadata](https://pypi.org/project/pymupdf/2.0/).

## Security track-record review

This is a review of public release and advisory history, not a claim that the engine
is vulnerability-free:

- **CVE-2026-82035 / GHSA-434w-92hw-f2m3 (high):** the GitHub Advisory Database
  describes path traversal and arbitrary file writes in the `extract_objects()`
  font-extraction CLI path in releases through 1.28.2. The upstream 2.0 changelog
  lists this issue as fixed. The old 1.26.7 renderer pin predates that fix, so the
  renderer workflow now installs 2.0. The current worker calls the Python rendering
  API directly and does not invoke the PyMuPDF CLI; that limits this specific call
  path but is not a substitute for using the fixed release.
- **CVE-2026-3029 / GHSA-cxqh-p2w9-fmr7 (moderate):** the advisory identifies an
  earlier path-traversal issue in the embedded CLI `get` command, affecting 1.26.5
  and fixed in 1.26.7. The existing pin included that fix, but the newer advisory
  above is why 1.26.7 is no longer selected.
- **Artifact provenance:** at review time, the PyPI 2.0 release page reported no provenance attestations for its files. An exact version pin does not authenticate
  the publisher or prove that a release has no undisclosed vulnerabilities. Recheck
  upstream release notes and advisories at every renderer update, and reassess
  artifact provenance when upgrading.

Sources: [GHSA-434w-92hw-f2m3](https://github.com/advisories/GHSA-434w-92hw-f2m3),
[GHSA-cxqh-p2w9-fmr7](https://github.com/advisories/GHSA-cxqh-p2w9-fmr7),
[PyMuPDF 2.0 changelog](https://pymupdf.io/changelog), and
[PyPI 2.0 provenance metadata](https://pypi.org/project/pymupdf/2.0/).

The selected renderer remains untrusted-input code: it must run only in the existing
bounded child process, after `_apply_limits()` and without a document pathname. The
renderer result never authorizes opening; mandatory scanner, quarantine, identity,
and admission checks remain independent. Process separation alone is not an OS-level
network or filesystem sandbox.

## License review

PyMuPDF and MuPDF are dual-licensed under the **GNU Affero General Public License
version 3 (AGPLv3)** or an **Artifex commercial license**. The repository's `LICENSE`
file is AGPLv3, so the open-source licensing route is only appropriate when the
application's distribution and use comply with all applicable AGPL obligations,
including applicable source and license-notice requirements. Proprietary or otherwise
incompatible use requires a separately obtained commercial license from Artifex.
This records the engineering license path; it is not a legal opinion or blanket
clearance for every deployment.

Sources: [PyMuPDF licensing](https://pymupdf.io/licensing),
[PyMuPDF project metadata](https://pypi.org/project/pymupdf/2.0/), and the repository
[AGPLv3 license](../LICENSE).

## Verification

The renderer workflow pins `pymupdf==2.0` on Linux and macOS. Its selection regression
checks the installed distribution version, the documented security and licensing
review, and that the worker applies resource limits before importing the native
renderer. The existing real-rendering suite continues to exercise the actual worker
API, bounds, and fail-closed behavior on both platforms.
