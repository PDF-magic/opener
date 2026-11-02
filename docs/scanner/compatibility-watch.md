# ClamAV compatibility watch (opener-1161)

PDF Magic Opener uses separately installed **ClamAV** and **FreshClam**. Its
runtime and installer currently accept stable **1.4** and **1.5** engines, with
matching scanner/updater branches. Unsupported or unverifiable versions fail
closed; neither a successful version probe nor this watch permits a PDF to open.

## Upstream release register

| Supported engine branch | Latest stable release reviewed for tracking | Source |
| --- | --- | --- |
| 1.4 LTS | `clamav-1.4.6` (2026-08-07) | [ClamAV 1.4.6](https://github.com/Cisco-Talos/clamav/releases/tag/clamav-1.4.6) |
| 1.5 | `clamav-1.5.4` (2026-08-07) | [ClamAV 1.5.4](https://github.com/Cisco-Talos/clamav/releases/tag/clamav-1.5.4) |

These are **release observation markers**, not a certificate that every macOS
installation or new release passed end-to-end compatibility acceptance. The
authoritative support policy is still enforced by `scan-and-open.py` and
`scripts/verify_installed_clamav.py`. ClamAV signature database revision and
the app's product version are **different** from the engine release number.

## Automated monitoring

The read-only [ClamAV compatibility watch](../../.github/workflows/clamav-compatibility-watch.yml)
runs every Monday, on manual dispatch, and as an offline contract test in PRs.
Its scheduled/manual step retrieves the public stable release inventory from
the official Cisco-Talos ClamAV GitHub repository. It compares the **newest
stable patch on each currently supported branch** to the reviewed marker in
`scripts/clamav_compatibility_watch.py` and flags a **newer stable branch**.
Missing or malformed inventory, network failure, and unreviewed stable releases
fail the monitoring job with an actionable review notice. Prereleases do not
change the stable marker. The inventory is bounded to the latest 100 releases,
so a supported branch disappearing from that window also fails for review.

A failing watch is an **alert for maintainer review**, not proof of a
vulnerability or a reason to weaken runtime checks. It makes no installed
scanner changes, fetches no executables or databases, runs no user-document
scan, and does not write preferences, signature files, quarantine, or caches.
The PR job is deterministic and does **not** depend on the upstream API.

Run a read-only manual check with:

```sh
python3 scripts/clamav_compatibility_watch.py
```

## Maintainer response to a change

1. Inspect the upstream [release notes](https://github.com/Cisco-Talos/clamav/releases)
   and [official documentation](https://docs.clamav.net/) for both supported
   branches, including engine security fixes, end-of-life announcements,
   breaking CLI/API changes, FreshClam protocol changes, and signature format
   or database compatibility changes. Handle sensitive security findings using
   [private reporting](../../SECURITY.md), not public issue details.
2. Check the actual macOS **ClamAV / FreshClam** versions, Homebrew or official
   installation paths, matching branch requirement, scanner arguments,
   timeout/output/exit semantics, EICAR rejection, incomplete-scan denial,
   signature staging and rollback, and fresh-signature enforcement. Run the
   existing version-support, post-install verification, scanner, and signature
   update regressions on the candidate; verify both architectures when
   relevant. A hosted Linux scanner smoke test is **not** a macOS acceptance.
3. If an engine update is compatible, document the test evidence and release
   impact before advancing only the reviewed marker. If a new branch is to be
   supported, separately review and change the installer/runtime allowlists,
   compatibility tests, and release notes. Do **not** automatically widen
   acceptance from observed upstream versions.
4. If incompatible or unverified, keep the scanner fail-closed and the marker
   unchanged; track remediation in a scoped issue or PR. Preserve existing
   installations and custom preferences. Do not downgrade scanner safety to
   silence this maintenance alert.

The separate [signature update process](signature-update-process.md) still
requires verified, staged updates and the **48-hour** freshness check; a new
engine release does not replace it or authorize opening any PDF.
