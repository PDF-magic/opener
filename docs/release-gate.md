# Fail-closed source-release gate (opener-1106)

The **Guarded GitHub release** workflow is the controlled, manual GitHub Releases
path. It does **not** sign, upload, or distribute browser extensions or macOS
applications. The [distribution audit](browser-extension-distribution.md) still
says **NOT RELEASE READY**, so release attempts currently fail even if CI is
green. Do not change that status until the actual channel-specific signing,
publisher identity, review, install, scanner, and quarantine prerequisites have
been independently satisfied.

Once those prerequisites are reviewed and explicitly cleared, create a
`vX.Y.Z` tag **at the current `main` commit** and dispatch the release workflow
on `main` with that tag. The gate refuses tags pointing anywhere else, stale
`main` commits, missing or duplicated critical GitHub Actions checks, check
API failures, and any required check that is pending, failed, skipped, or
cancelled. The required checks cover the scanner regressions, real EICAR
baseline, macOS build and native integration, macOS parser confinement, Chrome
package smoke, Python/JS lint, dependency vulnerability audit, and browser
extension distribution audit, and release-gate regressions. The release job repeats this verification
immediately before creating a **source-only** GitHub Release. No unsigned
browser packages are published by the workflow.

This gate deliberately uses only the built-in short-lived `github.token` and
public source/CI metadata. No signing credentials, user files, scanner
databases, or local preferences are opened. Run the read-only regression suite
with `PYTHONPATH=. python3 tests/general/release-check-gate.py -v`.

**Repository administration prerequisite:** GitHub Actions YAML cannot prevent
an administrator or other authorized publisher from using the GitHub UI/API to
publish a release directly, or from moving a tag. Configure and enforce
repository rules for release tags and publisher permissions outside this
source-only task. Do not claim that a successful check by itself establishes
production distribution readiness.
