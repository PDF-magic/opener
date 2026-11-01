# Dependency vulnerability checks (opener-1100)

The dedicated `Dependency vulnerability audit` GitHub Actions workflow runs on
pull requests, merge queue entries, pushes to `main`, weekly on Monday, and by
manual dispatch. It uses `pip-audit==2.10.1` to query published Python package
security advisories. This is separate from the offline dependency **licensing**
gate (`scripts/check_dependency_licenses.py`): an acceptable license says
nothing about vulnerability status.

The first live audit identified CVE-2026-119203, CVE-2026-119204, and
CVE-2026-119205 in the previously reviewed `pypdf==6.21.3` current pin.
All three are fixed by upstream in `pypdf==6.21.4`, so this same scoped
security change updates that pin and its offline license-review evidence.
The historical test-only pins are unchanged.

The workflow derives **every explicitly reviewed Python version** from the
license gate's checked CI requirements and workflow installs, then writes two
scoped temporary manifests (never committed):

- **Current optional Enhanced parser** (`requirements-enhanced-pdf.txt`):
  a **blocking** audit, including resolver-selected transitive dependencies.
  Any published vulnerability, malformed/incomplete scan, scanner failure or
  unreachable advisory service fails CI. This parser is not part of the
  installed Built-in scanner, but needs a secure reviewed pin before use.
- **Legacy CI-only test pins** (the other explicitly reviewed versions):
  a **reporting** audit, including transitive dependencies, with vulnerability
  IDs printed to the CI log. Existing known advisories in historical test pins
  are **not** silently discarded or represented as safe. An unavailable,
  malformed or incomplete scan fails CI. Existing findings do not block this
  scoped infrastructure change; separately review and upgrade those pins with
  their dependent tests before making that audit blocking. An upgrade also
  needs the existing license and compatibility review.

The audit parser independently rejects omitted or wrong-version reviewed
packages, invalid JSON, malformed vulnerability records and unexpected scanner
status. The regression suite exercises both blocking and reporting paths.
The WebExtension currently declares **no npm dependencies**, so there is no
third-party npm graph to audit. ClamAV and FreshClam are external, user-managed
native binaries installed from approved paths; Python package auditing cannot
attest to their macOS package-manager advisories, binary provenance or database
freshness. The existing mandatory scanner/version/signature safety gates are
unchanged. No user PDFs, user preferences, credential files or scanner binary
are accessed by this workflow. Network lookups are limited to CI's package
metadata/advisory service and the audit tool's isolated installation.

To run the deterministic local regression (no network):

```sh
PYTHONPATH=. python3 tests/general/dependency-vulnerabilities.py -v
```

To review current vulnerability status, inspect the `Audit pinned Python
dependencies` job. Resolve detected vulnerabilities by a separate, tested
version-pin change; do not weaken the scanner, ignore known critical findings
without review, or auto-upgrade test or runtime dependencies in CI.
