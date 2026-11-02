# PDF parser security advisory watch (opener-1162)

The [PDF parser advisory watch](../../.github/workflows/pdf-parser-advisories.yml)
runs deterministic contract tests on PRs, merge groups and `main` pushes. On
Tuesday at 08:37 UTC, or by manual workflow dispatch, it also queries the
[OSV vulnerability database](https://osv.dev/) for **each exact version** of
the reviewed Python PDF parser packages. Results remain in the workflow log
and GitHub Actions job summary; enable GitHub Actions failure notifications
for the repository so failed scheduled checks reach maintainers. A clean CI
contract test is *not* evidence that a live advisory query succeeded.

The watch derives pins from the existing license-review and dependency-audit
inventory rather than maintaining a second list of allowed versions:

- `pypdf==6.21.4`: current optional strict Enhanced structure parser;
  advisories affecting this pin fail the live watch. The installed Built-in
  ClamAV scan gate does **not** currently invoke this parser.
- `pypdf==5.9.0` and `pymupdf==2.0`: legacy / CI-only reviewed parser pins;
  matching advisories are printed as warnings for explicit triage, not silently
  treated as safe or automatically upgraded. These are not certified release
  dependencies. In particular, package/version declarations do not establish
  that a planned renderer is currently shipped.

A network error, malformed response, missing reviewed parser, bad advisory ID,
or unbounded/repeating pagination **fails** the live run rather than reporting
an all-clear. The OSV API returns *published, version-affected* advisories;
absence of matches is not proof of safety, coverage or exploitability. The
existing [dependency vulnerability audit](../dependency-vulnerabilities.md)
remains the independent blocking check for the active `pypdf` dependency.

## Sources and response

During maintenance reviews also consult the
[pypdf upstream security advisories](https://github.com/py-pdf/pypdf/security/advisories),
[PyMuPDF upstream advisories](https://github.com/pymupdf/PyMuPDF/security/advisories),
[ClamAV upstream advisories](https://github.com/Cisco-Talos/clamav/security/advisories),
and [NVD](https://nvd.nist.gov/), because the app's external ClamAV engine
parses PDFs but is **not** a Python package in the automated OSV watch.
The watch does not audit installed ClamAV binaries or signature databases;
continue using the established scanner/version/freshness checks.

For each reported identifier, a maintainer should review the linked public
OSV record and vendor notice, affected/fixed version ranges, the application's
actual parser use and reachable input paths, the severity and an appropriate
mitigation. Track the triage in the normal maintenance process; use private
security reporting for unpublished findings and never put exploit details or
private PDFs in public issue or CI logs. Make any dependency-pin change in a
separately tested, license-reviewed update; verify scanner isolation,
compatibility, parser resource limits and saved preferences before release.
**Do not disable mandatory scanning, weaken quarantine or silently alter
user-selected handling as an advisory response.**

Offline contract regression:

```sh
PYTHONPATH=. python3 tests/general/pdf-parser-advisories.py -v
```

The scheduled network check requires an available OSV service and is not run
on ordinary PRs; the workflow's manual-dispatch option supports an immediate
recheck after a new upstream disclosure.
