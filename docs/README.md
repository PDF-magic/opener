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

General installation, application, browser, and operational guides remain in this `docs/` directory.

- [Upgrade PDF Magic Opener](upgrade-process.md) — safely reinstall a trusted newer version, verify migration, and recover from a failed upgrade without resetting preferences.

- [Choose a PDF browser](select-browser.md) — select a verified post-scan browser in Settings or use the installed custom-application chooser.

- [macOS security controls](macos-security-controls.md) — what the scan gate does and does not do alongside Quarantine, Gatekeeper, notarization, XProtect, Launch Services, TCC, and SIP.\n- [Known unsupported PDF routes](browser-unsupported-routes.md) — the audited nine-browser, 27-route register of inactive or unverified automatic scan-before-render entry paths, with evidence and fail-closed next steps.

- [Antivirus signature limitations](scanner/signature-limitations.md) — why a clean ClamAV result does not guarantee safety, including freshness and cache limitations.

- [Browser download monitoring support](browser-download-monitoring-support.md) — which browsers expose relevant download events, what still needs verification, and why monitoring is inactive.

- [PDF structural analysis limitations](pdf/analysis-limitations.md) — what structural parsing can and cannot establish, supported limits, and the active protection boundary.

## Filename conventions

- Use lowercase **kebab-case** for documentation, scripts, and non-importable assets.
- When a folder already names a feature, do **not** repeat that prefix in the filename: `docs/pdf/structure-parser.md` rather than `docs/pdf/pdf-structure-parser.md`.
- Keep native tool conventions where names are part of an interface. Importable Python modules retain `snake_case.py`; Swift/Xcode source and project identifiers retain their established names. Those require separate, tested API or build-system migrations.
- GitHub Actions workflow files remain directly in `.github/workflows/`, as GitHub requires.

The CI documentation check verifies that pages in these feature folders retain kebab-case names, avoid duplicate directory prefixes, and point to existing local Markdown destinations.
