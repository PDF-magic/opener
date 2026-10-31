# Gatekeeper protections acceptance check (opener-0825)

PDF Magic Opener's malware scan is **not a substitute for macOS Gatekeeper**.
The existing scan gate retains `com.apple.quarantine` on clean, cached, blocked,
and unscannable PDFs. This task adds an independent **OS-level negative control**:
a quarantine-tagged, untrusted executable application must still be denied by
macOS security assessment.

## Automated coverage

Run `PYTHONPATH=. python3 tests/general/gatekeeper-protections.py -v`.

- Portable regressions reject false positives when `spctl --status` reports
  assessments disabled, unavailable, or ambiguous, or when the execution
  assessment is accepted or returns a usage error. An audit also fails if
  tracked runtime sources try to disable Gatekeeper via `spctl`.
- Native macOS CI compiles a harmless, truly unsigned Mach-O (removing any auto-applied ad-hoc signature) in a
  disposable `.app` bundle, attaches a **real** `com.apple.quarantine`
  marker, confirms `spctl --status` reports assessments enabled, and
  assesses its execution with `spctl --assess --type execute`.
  The check requires a negative OS assessment (an explicit rejection or code-signature validation failure), proves the xattr is
  unchanged, and confirms assessments remain enabled afterward.
- CI runs this alongside the existing
  [quarantine retention](../tests/general/retain-os-quarantine.py),
  [quarantined PDF opening](../tests/general/open-quarantined-pdf.py), and
  [quarantine-removal inventory](macos-quarantine-removal-inventory.md) checks.

No untrusted application or PDF is executed, and the fixture is deleted.
The check does **not** turn Gatekeeper on, disable it, grant exceptions,
rewrite trust rules, open Finder, run a real browser, or alter any installed
scanner or user preference. If a CI runner has security assessments disabled,
that is a **failed precondition**, never reported as a successful verification.

## Scope and limits

Gatekeeper primarily evaluates executable code, not whether PDF contents
are malware-free. This check tests an actual macOS policy decision for a
quarantined executable, and the existing tests independently verify PDF
quarantine retention and scan-gated handoff. It does not claim that GitHub
Actions can observe interactive Finder prompts or establish every third-party
PDF viewer's behavior.

Apple references:
- [Use spctl for Gatekeeper assessment](https://developer.apple.com/library/archive/documentation/Security/Conceptual/CodeSigningGuide/Procedures/Procedures.html)
- [Test a downloaded Developer ID app](https://help.apple.com/xcode/mac/current/en.lproj/dev1cc22a95c.html)
