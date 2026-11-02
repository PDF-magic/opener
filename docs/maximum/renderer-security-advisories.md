# Renderer security-advisory tracking (opener-1163)

Review baseline: 2026-11-01. Scope: **Maximum-only** isolated page renderer.
This is a monitoring and triage record, **not** proof that renderer code is safe
and **not** approval to enable the currently non-selectable Maximum tier.

## Pinned components and two separate advisory surfaces

- Python distribution: **PyMuPDF 2.0**, exactly pinned by the real renderer
  install in `.github/workflows/consolidated-checks.yml` (`--no-deps`).
- Bundled native engine: **MuPDF 1.28.5**, per the upstream PyMuPDF 2.0
  [changelog](https://pymupdf.io/changelog) and
  [renderer selection review](renderer-selection.md).

Every pull request, main push, weekly Monday schedule and manual dispatch
runs the dedicated `dependency-vulnerabilities.yml` audit. Its new
**blocking renderer check** derives the reviewed `pymupdf` pin from the
existing license/inventory gate, requests fresh PyPI security advisories with
`pip-audit --strict --no-deps --disable-pip`, and rejects missing, malformed,
wrong-version or vulnerable results. An unavailable advisory lookup fails CI.
The existing Enhanced parser audit remains separate and blocking; historical
CI-only test pins remain separately reported.

**Important limitation:** the Python package audit **does not cover embedded
native MuPDF advisories** unless they are independently recorded against the
PyMuPDF distribution. A successful PyMuPDF audit must not be interpreted as
clearance for the embedded engine. The maintainer must also check these
independent sources at least weekly and **before any renderer release/update**:

- [MuPDF upstream release history](https://mupdf.com/releases/history) and
  [Artifex MuPDF issue tracker](https://bugs.ghostscript.com/).
- [Debian's MuPDF source-package security tracker](https://security-tracker.debian.org/tracker/source-package/mupdf),
  including linked CVE records (distribution fix statuses are not direct
  evidence that the **bundled** engine was patched).
- [GitHub's PyMuPDF advisory search](https://github.com/advisories?query=PyMuPDF)
  and [PyMuPDF upstream changelog](https://pymupdf.io/changelog).

Do not automatically upgrade a renderer wheel, use an unreviewed version,
disable checks, or modify scan-before-open / quarantine / viewer preferences
in response to an advisory.

## Open baseline for triage

| Advisory | Affected bundled engine | Recorded assessment | Next action |
| --- | --- | --- | --- |
| [CVE-2026-112036](https://security-tracker.debian.org/tracker/CVE-2026-112036) | Reported against **MuPDF through 1.28.5** (double free in PDF signature locking, `free_char_list`) | **Not verified fixed** in the bundled 1.28.5 build. The Debian tracker lists an upstream patch reference but does not attest to the PyMuPDF wheel. Native-engine risk remains unresolved; this is not silently waived by a clean `pip-audit` result. | Confirm whether the current rendering API reaches the affected path; obtain a verified fixed upstream release/build, review licensing and security history, and run the isolated-renderer regression before considering an upgrade. |

The known native advisory is **recorded, not auto-suppressed or claimed
remediated**. The Python distribution scan blocks newly reported PyMuPDF
vulnerabilities. This native baseline needs separate maintainer security
triage; do not publicly include exploit samples or sensitive inputs.

## Triage each new advisory

1. Record the advisory ID/URL, first-seen and review dates, source, affected
   versions, severity, and whether it applies to PyMuPDF, native MuPDF, or
   both. Check upstream fixes and any conflicting version claims.
2. Assess reachability in the **bounded native rendering API**, not solely
   CLI utilities; treat unknown reachability as unresolved. Independently
   assess memory corruption, denial of service, sandbox escape and potential
   impact on the planned Maximum workflow. Do not treat isolation as a fix.
3. If the pinned component is affected, **block release/use of the affected
   optional renderer** pending security review and a verified mitigation.
   Use a separate focused task to change its version after testing engine
   behavior, package provenance, AGPL/commercial license obligations and
   the existing process limits. Never bypass the mandatory ClamAV gate.
4. Record the disposition (affected/fixed/not applicable/unresolved), linked
   upstream evidence and tested version. Recheck after upstream releases
   and whenever this repository changes the renderer pin. Do not close
   an advisory merely because a general package vulnerability scanner
   returned zero findings.

The isolated renderer remains Maximum-only and cannot authorize file
opening. For reporting nonpublic details, use [the security policy](../../SECURITY.md),
not a public PR comment or CI log.
