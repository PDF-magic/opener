# Security fix prioritization (opener-1169)

This is the maintainer triage and scheduling policy for security fixes in PDF Magic
Opener, including the macOS scan-before-open gate, ClamAV integration, signature
updates, native messaging, browser extensions, PDF processing, dependencies,
and build/distribution tooling. It does **not** enable an updater or change
enforced runtime protections.

Report suspected vulnerabilities using the **private** process in
[SECURITY.md](../SECURITY.md). Do not create public issues, pull requests, CI
logs, or test fixtures containing undisclosed exploit details, malicious PDFs,
private documents, credentials, or sensitive diagnostics.

## Assess and assign priority

For each finding, maintainers record the affected component and versions,
whether the code is shipped, enabled, or still experimental, reachable attack
surfaces and prerequisites, impact on confidentiality, integrity and
availability, evidence of exploitation, and the availability of an upstream fix
or safe mitigation. Consider the trust boundary: a malicious PDF, remote page,
untrusted extension message, external dependency, or compromised update source
can have different impact from a local-only, privileged configuration error.

Use reproducible **non-destructive** evidence, upstream advisories and CVSS
scores as inputs, **not** as automatic priority labels. Assess **actual
reachability and existing mitigations**: a high-scoring upstream flaw in unused
code may be less urgent than a lower-scoring bypass of the installed scan gate.
If reachability, impact or mitigation efficacy is uncertain, assign the
**higher plausible priority provisionally** until evidence establishes a
narrower scope.

| Priority | Classification | Action and scheduling |
| --- | --- | --- |
| **P0 — Emergency** | Active exploitation, or credible immediately exploitable compromise of the scan-before-open gate, execution boundary, native-message trust boundary, update integrity, or sensitive user data. | Interrupt feature and routine maintenance work; investigate and safely contain immediately. Block affected releases and opening paths until a tested fix or fail-closed containment exists. |
| **P1 — High** | Practical, high-impact vulnerability on a reachable supported path without confirmed active exploitation, including bypass of a protective check or significant data exposure. | Start an expedited fix ahead of normal updates and feature work; hold any affected release until remediation or verified fail-closed containment is complete. |
| **P2 — Moderate** | Real security impact with constrained reachability, unusual prerequisites, or independently verified existing mitigations, and no evidence requiring P0/P1. | Schedule in the next planned maintenance cycle before discretionary hardening; reassess at least monthly and whenever new exploitation or exposure evidence appears. |
| **P3 — Low** | Defense-in-depth or low-impact issue with no demonstrated practical security boundary failure. | Track for a later reviewed maintenance change; reassess at least monthly or if the affected surface becomes reachable. |

Priorities are **relative work-order rules, not guaranteed response or repair
deadlines**. P0 and P1 never wait for the weekly dependency audit or monthly
review. An unavailable maintainer, uncertain reproduction, absence of a CVE,
or passing CI does not automatically reduce priority. When several fixes share
a priority, address active exploitation, exposed installed paths, breadth of
affected users and ease of exploitation first.

## Escalation, remediation and disclosure

1. Keep a confidential triage record of the evidence, affected versions,
   priority, ownership, safe mitigation, verification plan and next review.
   Limit access to those handling the report. Use sanitized public tracking
   only when it does not reveal actionable vulnerability information.
2. Reassess **immediately** on new exploitation reports, reachable attack paths,
   published upstream fixes, failed mitigations, or scope expansion. Escalate to
   P0/P1 as appropriate; revise downward only with documented supporting
   evidence. A dependency advisory requires impact review rather than an
   automatic unattended version bump.
3. Prefer a narrowly scoped, reviewed security fix and regression test. For a
   compromised exposed entry path, disable or restrict **only that path** if
   doing so is verified safe. Never fall back to unscanned opening, stale
   signatures, unsigned or unverified helpers, disabled quarantine or
   file-integrity checks, or broader browser/native-messaging permissions.
   Missing or unverified protections **fail closed**.
4. Before accepting a remediation, verify the original failure with inert
   regression evidence and the applicable scanner, quarantine, filesystem,
   browser, native-host, dependency and macOS tests. Require applicable CI,
   a source/compatibility review, and the existing
   [release gate](release-gate.md). Preserve user-selected PDF browser,
   protection preferences, signature databases, custom signatures and Finder
   customizations. If an update fails, retain the last verified working
   installation without weakening the gate; follow the
   [upgrade process](upgrade-process.md).
5. Coordinate any advisory and external publication with the reporter using
   [the private reporting process](../SECURITY.md). Do not promise a public
   disclosure date or publish exploit material before coordination. If no safe
   fix is ready, keep the affected opening or distribution path blocked and
   explicitly reassess the risk; do not silently accept an exploitable bypass.

The [dependency update policy](dependency-update-policy.md) governs version
changes and their owner, while the
[dependency vulnerability audit](dependency-vulnerabilities.md) and separate
[parser advisory watch](pdf/parser-security-advisories.md) supply findings.
Those checks cannot establish exploitability, replace human triage, or
authorize a release. This prioritization policy does not change scanner code,
extension behavior, user configuration, or existing distribution readiness.
