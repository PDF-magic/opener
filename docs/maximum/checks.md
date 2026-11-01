# What Maximum checks (opener-1114)

**Maximum is a planned, preview-only protection level**, not a selectable or
active scanner mode. Its structured policy inherits every Enhanced requirement,
including Enhanced's optional check promoted to **required**. The installed
**Built-in** ClamAV gate is still the only enforced opening policy. The
"Current" labels below describe that Built-in safety floor, **not** an
operational Maximum pipeline.

## Required checks

- **ClamAV malware scan gate** (`clamav_scan_gate`) — **Current Built-in
  safeguard.** Require a verified local ClamAV verdict before opening a PDF;
  detections, missing results, scan errors and timeouts block opening. A cached
  clean verdict is only usable under the existing validated cache policy.
- **Signature freshness** (`signature_freshness`) — **Current Built-in
  safeguard.** Require a successful malware-definition check within **48
  hours**. Stale or unverifiable definitions block opening, even when a clean
  result was previously cached.
- **File integrity** (`file_integrity`) — **Current Built-in safeguard.**
  Verify the scanned file's identity and contents before handoff; changed or
  replaced files cannot reuse an earlier clean verdict.
- **Fail-closed verified opening** (`fail_closed_handoff`) — **Current
  Built-in safeguard.** Open only after required checks succeed and the
  selected PDF-capable application is verified. Errors never silently choose
  another destination, remove macOS quarantine, or authorize opening.
- **PDF structure validation** (`pdf_structure_validation`) — **Planned,
  not enforced as a Maximum check.** This is required in Enhanced and
  inherited by Maximum. Strict passive PDF structure inspection may detect
  malformed, ambiguous or unsupported document features, but separate parser
  utilities do not make this a mandatory installed scan stage.
- **Isolated behavior analysis** (`isolated_behavior_analysis`) — **Planned,
  not enforced as a Maximum check.** Enhanced lists this as optional; Maximum
  promotes it to required without changing its planned status. Isolated,
  resource-bounded *passive* PDF inspection must not execute PDF scripts,
  launch attachments, contact URLs or grant an opening verdict. Existing
  isolated-inspector components do not yet form the enforced Maximum engine.

## Optional checks

**None.** Maximum's structured policy has no optional controls: it requires
all four current Built-in controls plus the two planned controls above.
Inheriting and promoting Enhanced's optional isolated analysis does **not**
turn that analysis into a currently enforced check. See the
[Enhanced inheritance contract](enhanced-inheritance.md) and the
[policy comparison](../protection/settings-checks.md).

## Related Maximum-only processing (not an active profile)

The repository also contains separate building blocks for
[process-isolated PDF analysis](isolated-analysis.md),
[isolated rendering](isolated-renderer.md), and
[rasterized sanitized-copy generation](sanitized-copy.md). These are **not
additional active checks in the six-control structured policy** and do not
amount to a complete, deployed Maximum scanner or OS sandbox.

For supported documents, a future Maximum workflow may regenerate a
**separate image-only PDF** to remove active content such as JavaScript,
embedded attachments, forms and launch actions. Conversion can also remove
searchable text, links, annotations, metadata, and digital signatures or
change visual fidelity. Unsupported or failed conversion must block rather
than fall back to the original. A verified generated copy **still needs a
separate fresh ClamAV scan and file-integrity validation before opening**;
a sanitized-copy offer alone never authorizes launch. The original must not
be silently overwritten or opened in its place. See
[safe-copy handoff](safe-copy-handoff.md).

## Availability and safety boundary

All three named tiers (Standard, Enhanced and Maximum) are **non-selectable**
for effective scanning. Previewing Maximum does not activate its two planned
mandatory controls, select a new mode, persist an effective policy, convert a
PDF, or change the user-selected destination. Completing and integrating the
planned inspections, renderer isolation, sanitization and verified opening
path needs separate work and testing. The existing **Built-in** scanner
retains its malware, freshness, file-integrity, quarantine, cache and
fail-closed handoff requirements. Even a clean ClamAV result is not proof
that a document is harmless.
