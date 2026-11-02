# Technical documentation

The reference pages are grouped by feature rather than keeping every page in one flat directory.

| Area | Contents |
| --- | --- |
| [Enhanced](enhanced/) | Analysis and inspection behavior |
| [Maximum](maximum/checks.md) | What Maximum checks, [sanitization limits](maximum/limitations.md), plus isolation, conversion, and fidelity |
| [PDF](pdf/) | PDF structures, metadata, embedded content, and parsing |
| [Performance](performance/results.md) | Recorded benchmark observations, CI provenance, and measurement limits |
| [Protection](protection/) | Protection policies, choices, and exceptions |
| [Scanner](scanner/) | Scanner arguments, safety, and failure handling |

For a user-facing summary of the planned tier, see [Enhanced checks](enhanced/checks.md), including which safeguards are currently enforced and which inspections are unavailable.

For manual source-based application updates, see [Application update delivery](application-update-delivery.md). There is no planned binary update, signing, or automatic-update channel.

General installation, application, browser, and operational guides remain in this `docs/` directory.

- [Install PDF Magic Opener from source](installation-path.md) — supported per-user installation steps, prerequisites, post-install verification, and public-release limitations.

- [Clean macOS installation verification](clean-macos-install.md) — guarded notarized first-install verification on a fresh runner, plus real clean-Mac acceptance steps.

- [Developer ID signing](developer-id-signing.md) — sign and verify staged macOS distribution binaries and helper applications without modifying the installed scan gate.

- [Troubleshooting](troubleshooting.md) — diagnose safe installation, scan, signature, PDF handler, and browser-handoff failures without bypassing protections.

- [Handling quarantined files](quarantined-files.md) — what macOS File Quarantine means for clean, blocked, and unscannable managed opens, plus safe troubleshooting.

- [Dependency update policy](dependency-update-policy.md) — review cadence, approved update channels, verification, and safe rollback for ClamAV, definitions, Python, helpers, CI tools, and extensions.

- [Upgrade PDF Magic Opener](upgrade-process.md) — safely reinstall a trusted newer version, verify migration, and recover from a failed upgrade without resetting preferences.

- [Supported application versions](../SECURITY.md#supported-versions) — current support status for older development builds and the policy for future stable releases.

- [Choose a PDF browser](select-browser.md) — select a verified post-scan browser in Settings or use the installed custom-application chooser.

- [macOS security controls](macos-security-controls.md) — what the scan gate does and does not do alongside Quarantine, Gatekeeper, notarization, XProtect, Launch Services, TCC, and SIP.\n- [Known unsupported PDF routes](browser-unsupported-routes.md) — the audited nine-browser, 27-route register of inactive or unverified automatic scan-before-render entry paths, with evidence and fail-closed next steps.

- [Antivirus signature limitations](scanner/signature-limitations.md) — why a clean ClamAV result does not guarantee safety, including freshness and cache limitations.
- [Offline behavior](offline-behavior.md) — when local scanning works without a network, how the 48-hour signature gate applies, and what remains online-only.


- [Signature update process](scanner/signature-update-process.md) — how FreshClam checks, safely verifies, publishes, and reports signature updates.

- [ClamAV compatibility watch](scanner/compatibility-watch.md) — track upstream stable engine releases and require deliberate compatibility review without changing scanner safety.

- [Scanner errors and recovery](scanner/errors.md) — distinguish failed and incomplete scans from malware findings and safely recover without bypassing protection.

- [Browser download monitoring support](browser-download-monitoring-support.md) — which browsers expose relevant download events, what still needs verification, and why monitoring is inactive.

- [PDF structural analysis limitations](pdf/analysis-limitations.md) — what structural parsing can and cannot establish, supported limits, and the active protection boundary.
- [Browser extension update delivery](extension-update-delivery.md) — manual Chromium and Firefox reloads, Safari app replacement, and version, identity, and scanner-safety requirements.
- [Browser extension installation](browser-extension-installation.md) — local development loading for Chromium-family browsers, Firefox, and Safari; release and scanner-safety limits.


- [Compromised release revocation](release-revocation.md) — withdraw suspect releases, stop distribution, warn users, and verify safe recovery.
- [Security reporting process](../SECURITY.md) — how to privately disclose suspected vulnerabilities without posting exploit details publicly.
- [Security fix prioritization](security-fix-prioritization.md) — severity and exposure-based security fix work order, escalation, safe verification, and disclosure.

## Filename conventions

- Use lowercase **kebab-case** for documentation, scripts, and non-importable assets.
- When a folder already names a feature, do **not** repeat that prefix in the filename: `docs/pdf/structure-parser.md` rather than `docs/pdf/pdf-structure-parser.md`.
- Keep native tool conventions where names are part of an interface. Importable Python modules retain `snake_case.py`; Swift/Xcode source and project identifiers retain their established names. Those require separate, tested API or build-system migrations.
- GitHub Actions workflow files remain directly in `.github/workflows/`, as GitHub requires.

The CI documentation check verifies that pages in these feature folders retain kebab-case names, avoid duplicate directory prefixes, and point to existing local Markdown destinations.

- [Development release notes](release-notes.md) — public notes about the current unreleased source tree, including security protections and distribution limits.

For distribution policy, see the [release versioning scheme](release-versioning.md), including stable tags and component versions.

- [Firefox WebExtension API watch](firefox-api-watch.md) — review upstream Firefox API and manifest compatibility changes without mutating the inactive extension.

- [PDF parser security advisory watch](pdf/parser-security-advisories.md) — scheduled advisory monitoring and triage for reviewed parser versions.

- [Safari extension API change watch](safari-extension-api-watch.md) — read-only weekly WebKit release monitoring, offline CI checks, and manual Safari compatibility review.
