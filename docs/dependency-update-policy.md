# Dependency update policy (opener-1160)

Dependency updates are **reviewed changes**, not an untrusted background update
channel. The app does not automatically replace its scanner engine, install
Python packages into an end-user environment, or update native helpers.
This document assigns each dependency to its actual update mechanism; it does
not change any scanner, installation, browser extension, or release behavior.

## Ownership and update channels

| Dependency | How it is updated | Review and acceptance |
| --- | --- | --- |
| ClamAV engine (`clamscan`) and its `freshclam` executable | **Externally managed by the user**, through the already chosen Homebrew or trusted upstream installation channel. A user may deliberately upgrade the existing installation with that provider's supported procedure; the PDF Magic Opener installer does not silently replace a detected compatible engine or initiate `brew upgrade`. Homebrew remains only an explicitly consented missing-engine installation fallback. | Check authentic source and compatibility on arm64/x86_64 macOS; keep the runtime's fixed scanner locations, safe executable/symlink validation, supported ClamAV version check and same-installation FreshClam check. An absent, incompatible, or unverified engine fails closed. Do not bundle, downgrade, or substitute another engine automatically. |
| ClamAV malware definitions (`main` and `daily`) | **FreshClam**, not the application or a package-manager upgrade. The existing per-user LaunchAgent checks every **four hours** while logged in; an explicit **Update Signatures Now** action uses the same guarded updater. | Continue locked, private staging, validation with ClamAV, atomic promotion, preservation of previous usable definitions on failure, and the mandatory **48-hour** signature-freshness gate before managed opening. An attempted update is not a successful update. |
| Native Swift app and reviewed helper executables | Updated together only through the separately approved, trusted native application source/release upgrade procedure. Rebuild and check helper allowlists and signing when public distribution becomes eligible. | Review source, helper identities, package contents, signing/notarization and upgrade/migration tests; preserve user preferences, custom Finder actions, scanner files and rollback behavior. No independent helper downloader. |
| Optional Enhanced Python parser (`pypdf`) and pinned CI-only Python tools | A maintainer proposes a **version-pinned PR** to `requirements-enhanced-pdf.txt` or the relevant CI workflow, never an unreviewed `pip install -U` in an installed scanner. Update the reviewed versions and license evidence in `scripts/check_dependency_licenses.py` and `docs/dependency-licenses.json` together. | Verify upstream changelog, security advisories, resolved transitive dependencies, license obligations, supported Python versions and affected parser/CI tests. The current optional parser is **not** part of the active Built-in scan gate; upgrading it does not enable Enhanced or Maximum. |
| Browser WebExtension | Its `extensions/webextension/package.json` currently declares **no npm dependencies**. Any proposed runtime, development or transitive package requires a separate reviewed PR, explicit version/lock and supply-chain/license/vulnerability assessment before the dependency-free contract changes. | Rebuild and test the extensions and manifests; release/sign/store updates remain separate. No automatic package installation or change to browser permissions. |
| GitHub Actions and build/test tooling | Upgrade pinned tool versions and action references in an explicit reviewed PR, with upstream provenance and permission/compatibility review. Runner-image and external tool changes also require validation when they affect reproducibility. | Run affected CI and security tests before accepting changes; do not confuse CI tooling upgrades with user-facing app or scanner updates. |

The existing [dependency delivery decision](dependency-delivery-evaluation.md)
explains why the scanner engine stays externally managed and only the reviewed
native helpers may be staged as a bundle. Changes to that ownership model
need a separate security/distribution decision, not a routine version bump.

## Review schedule and change procedure

- **Every Monday:** the existing
  [dependency vulnerability audit](dependency-vulnerabilities.md) checks
  reviewed Python pins, including the current optional parser (blocking) and
  legacy CI-only pins (reporting). It also runs on PRs and pushes. A reported
  legacy finding is a tracked risk, **not** an assertion that the version is safe.
- **At least monthly:** maintainers inspect upstream release notes, vendor
  support/EOL notices, ClamAV security bulletins, parser and build-tool
  advisories, and outstanding legacy CI-only findings. Security advisories,
  unsupported engine branches and reproducible breakages trigger review
  outside this cadence; prioritize security fixes rather than waiting for
  the monthly review.
- **For each proposed change:** identify the exact upstream version and
  provenance; describe security rationale, risk, affected platforms and
  rollback; update explicit pins and evidence together where applicable;
  verify license and vulnerability status; exercise affected scanner,
  installation, parser, helper, extension and macOS build checks in CI.
  Preserve release notes and version alignment when a product release is
  needed. Do not auto-merge a dependency-only PR because an advisory tool
  proposed it.
- **Before release:** require all applicable CI gates, human review of
  advisory/compatibility results, and the existing
  [release gate](release-gate.md). CI success is not proof that unsigned
  development packages are safe for public installation. A failed or
  incompatible upgrade is held or reverted in source; use the documented
  [upgrade and recovery procedure](upgrade-process.md) for already installed
  applications instead of resetting user settings.

Use these existing offline/CI checks for version changes:

```sh
python3 scripts/check_dependency_licenses.py
PYTHONPATH=. python3 tests/general/dependency-licensing.py -v
PYTHONPATH=. python3 tests/general/dependency-vulnerabilities.py -v
PYTHONPATH=. python3 tests/dependencies/delivery-evaluation.py -v
```

The scheduled `Dependency vulnerability audit` additionally invokes pinned
`pip-audit` online and **fails** on an advisory for the current parser or on
incomplete/unavailable results. Do not bypass a failing audit by ignoring
findings or suppressing failure codes. Review legacy CI findings and upgrade
those versions in a separate tested change.

## Failed updates and security boundaries

A package-manager upgrade, ClamAV version string, successful FreshClam run,
new Python pin, or newer native bundle never authorizes a PDF to open.
Every managed open still requires valid scanner binaries, usable **fresh**
signatures, complete scanning, file-integrity checks, quarantine handling
and a verified destination. Missing or unsupported dependencies block
opening rather than switching to an unsafe fallback.

Keep user-selected browsers, protection preferences, signature configuration,
custom signatures, Finder customizations and previous working installation
intact across upgrade/recovery. Do not overwrite a user's externally managed
ClamAV install, silently modify its update policy, delete signature databases,
or replace verified helpers in place without the established migration gate.

See the [signature update process](scanner/signature-update-process.md),
[ClamAV Homebrew decision](clamav-homebrew-decision.md),
[dependency licensing](dependency-licensing.md) and
[application upgrade guide](upgrade-process.md) for implementation details.
