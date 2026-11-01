# Enhanced protection: what it checks (opener-1113)

**Availability: Enhanced is planned and not selectable.** The installed
**Built-in** ClamAV scan gate is the only active protection policy. The
entries marked `current` below describe safeguards enforced by that
existing gate, **not** proof that an Enhanced scan runs today. An isolated
inspection component or a successful structural analysis does not establish
that a document is safe to open.

## Policy checks

The source of truth is the non-executable
[`protection_policy_definitions.py`](../../protection_policy_definitions.py)
contract. Enhanced requires the four Built-in safeguards **plus** a planned
PDF-structure check. Its behavior-analysis check is optional and planned.

| Control ID | Enhanced policy | Availability | What it checks |
| --- | --- | --- | --- |
| `clamav_scan_gate` | Required | `current` | Scans the file with ClamAV and blocks malware detections or failed/incomplete scans. |
| `signature_freshness` | Required | `current` | Requires usable, sufficiently recent malware signatures before the scan can approve an open. |
| `file_integrity` | Required | `current` | Verifies the scanned file has not changed before the handoff. |
| `fail_closed_handoff` | Required | `current` | Blocks unsafe or unverified handoffs and preserves quarantine/verified PDF-app selection. |
| `pdf_structure_validation` | Required | `planned` | Would validate PDF syntax, object relationships and structural evidence; it is not integrated into the active scan gate. |
| `isolated_behavior_analysis` | Optional | `planned` | Would assess potentially active PDF behavior in isolation; it is not an executable or enabled scan stage. |

**Required** means the control must succeed before a future Enhanced policy
could make an opening decision. **Optional** does not relax any required
checks. The future profile must never silently skip unavailable required
checks, downgrade to a weaker tier, or authorize opening on inconclusive
evidence.

## What the separate PDF inspection components examine

The repository includes independent, passive analysis components and
reporting contracts. They are building blocks for a future orchestrated
Enhanced scan, **not a guarantee that all these checks execute today**:

- **Structure and revisions:** PDF headers, cross-reference tables/streams,
  page trees, object streams and references; malformed, conflicting or
  ambiguous structures, excessive nesting or object counts, suspicious
  revision history and unsupported features. See
  [structure parsing](../pdf/structure-parser.md) and
  [blocking policy](blocking-policy.md).
- **Embedded content:** attachment declarations, names, types and bounded
  embedded streams. A standalone embedded-file inspector can pass extracted
  bytes to ClamAV, but it is **not wired into the installed gate**. See
  [embedded-file inspection](embedded-file-inspection.md).
- **Potentially active content:** JavaScript actions, automatic actions,
  form and annotation actions, rich media, external-launch requests and
  embedded URLs. Inspection is descriptive; it does **not** execute scripts,
  open attachments, follow links or issue external requests. See the
  [additional-inspection plan](additional-inspections.md).
- **Unverifiable input:** encrypted/password-protected PDFs, incomplete or
  unsupported parsing, exceeded resource limits, missing dependencies,
  scanner errors, and missing expected inspection stages cannot be treated
  as successful inspections. See [inconclusive results](inconclusive-results.md).

A reported suspicious action is **not necessarily malware**. Findings can
require review or block opening, but a report with no findings is
**not a clean ClamAV result**. The [structured findings contract](../structured-enhanced-findings.md)
and [blocking policy](blocking-policy.md) do not grant opening permission.
Future integration must preserve the current scanner, signature-freshness,
file-integrity, quarantine and verified-handoff requirements, as well as
existing application preferences and custom viewer selections.

For a comparison with Standard and Maximum, see
[protection settings checks](../protection/settings-checks.md) and
[activation blockers](../protection/profile-dependencies.md).
