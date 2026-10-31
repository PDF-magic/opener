# Dependency delivery evaluation (opener-0958)

**Decision, 2026-10-31:** Retain a **mixed, explicitly scoped model** rather
than make every dependency application-managed or ship a bundled scanner.
This evaluates distribution approaches; it does not approve a new installation
path, change any supported executable version, or activate a planned profile.

## Alternatives and ownership

| Dependency | External / system-managed | App-managed installation and updates | Bundled in app | Current decision |
| --- | --- | --- | --- | --- |
| ClamAV `clamscan` engine | Homebrew or independently installed upstream macOS tools; user retains package update policy | Installer could own engine downloads and upgrades, requiring authenticated artifacts, version pinning, rollback and multi-architecture builds | Shipping native engine plus libraries would require binary provenance, vulnerability response, licensing, signing/notarization, architecture testing and independent patch delivery | **External managed: selected.** Respect the three established paths, with Homebrew only a fallback for a missing engine; never treat detection alone as authorization to scan/open |
| ClamAV definitions and FreshClam | Existing FreshClam maintains signatures in per-user storage, with staged validation, locking and atomic promotion | App-owned definitions feed would duplicate or replace upstream update infrastructure and require authenticity/freshness and rollback handling | Static signatures age rapidly and cannot replace the current 48-hour freshness check | **FreshClam-managed: selected.** Keep independent updates and the mandatory freshness gate; do not embed a static substitute |
| Reviewed Swift helper executables | Requiring independently installed helpers increases setup and version-skew risk | Existing installer compiles and installs its reviewed helpers from local source | The separate preferences-app packager already stages an allowlisted set of compiled Mach-O helpers, but its unsigned staging output is not a trusted release and does not register a PDF handler | **Bundled staging: appropriate only for reviewed native helpers**, subject to exact allowlist, identity, executable validation, signing/notarization and release review before distribution; retain the separately installed scan gate |
| Optional Enhanced PDF parser (`pypdf`) | Pin in the test/optional Enhanced dependency file, not in the Built-in runtime scanner | A future tier-specific managed environment would need reproducible resolution, hash/provenance checks and security updates | Bundling a Python runtime/parser would increase supply-chain and interpreter-patching obligations; it cannot by itself activate Enhanced | **Test-only optional pin: selected.** Enhanced and Maximum remain unavailable until their mandatory engines are integrated and fail closed |

**Tradeoffs:** External engine management reduces application binary footprint and
avoids shadow update channels, but requires a supported installed binary,
verified version and signatures. An app-managed engine could simplify first
run but would assume secure download, dependency resolution, upgrade and
rollback responsibilities. Bundling increases offline installation
predictability but also multiplies OS/CPU coverage, security patch latency,
binary size, redistribution compliance and release-signing obligations.
These are **delivery** properties, not substitutes for scanner safety.

## Boundaries that must hold

1. `scan-and-open.py` accepts only its fixed ClamAV paths and checks the
   executable and version before the existing signature, scan, cache,
   file-integrity, quarantine and verified-opening gates. No `PATH`
   discovery, packaged scanner binary or missing-dependency fallback may
   implicitly authorize a PDF.
2. `update-malware-signatures.sh` invokes an external FreshClam executable
   against a private staged database, validates before promotion and
   preserves the usable live definitions on failure. Do not replace it with
   bundled signature snapshots.
3. `scripts/package_application_helpers.py` stages only its reviewed native
   helper allowlist. The separate `PDFOpener` scan-handler bundle, ClamAV,
   FreshClam and `pypdf` are **not** inside this helper package. This
   is not a signed/notarized release installer.
4. `requirements-enhanced-pdf.txt` is an optional pinned CI/parser dependency,
   not part of the installed Built-in scan path. It grants no permission to
   select Enhanced/Maximum or to skip a mandatory engine.

## Release decision gate for reconsideration

A proposal to manage or bundle a protection dependency must first document:
upstream and artifact provenance (including hashes/signatures and
redistribution/license review); supported macOS versions and arm64/x86_64
builds; vulnerability and signature update service-level targets; safe
atomic upgrade/rollback and uninstall ownership; code signing and
notarization; installation footprint/offline behavior; no overwrite of
existing user-installed tools/preferences; and automated failure-path
tests proving an unavailable, corrupt or stale dependency **cannot** scan,
cache clean, release quarantine or launch a PDF. Changing any delivery
mode requires its own scoped implementation and security review.

## Related scope

The Homebrew *default installation route* decision is opener-0957
(`docs/clamav-homebrew-decision.md`, PR #648). Homebrew availability
detection is separately opener-0954 (PR #641). This evaluation does not
reimplement those decisions or modify the installer or runtime.

Supporting implementation: `install-allow-and-open.sh`,
`scan-and-open.py`, `update-malware-signatures.sh`,
`scripts/package_application_helpers.py`,
`requirements-enhanced-pdf.txt` and
`docs/protection/profile-dependencies.md`.
