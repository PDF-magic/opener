# Limitations of antivirus signatures (opener-1115)

PDF Magic Opener uses the locally installed **ClamAV** engine and its malware
definitions as a mandatory check before a **managed** PDF opening. ClamAV's
signature and engine rules can recognize known threats, but **a clean verdict
means no threat was detected, not that a document is safe**. Signature scanning
is one layer of defense, not proof of a harmless PDF.

## What signatures cannot establish

- **Unknown or newly emerging malware:** a threat may have no matching
  signature yet. Even recently checked definitions cannot guarantee coverage
  against new, targeted, or previously unseen attacks.
- **Evasion and disguised content:** packed, obfuscated, polymorphic, or
  otherwise modified malicious content can escape a signature match.
  A malicious document may appear ordinary until it is interpreted by a PDF
  viewer or another component.
- **PDF behavior and content semantics:** a clean ClamAV result does not certify
  PDF structure, embedded scripts, links, external requests, attachments, or
  social-engineering content as benign. Signature matching is not equivalent to
  executing the document safely in a sandbox or completing a structural audit.
  Additional Standard/Enhanced/Maximum inspections are **not active** merely
  because those protection levels appear in the UI.
- **Unscannable input:** encryption, inaccessible bytes, scanner errors,
  unsupported or exceeded engine limits, and timeouts can prevent a complete
  verdict. The opener **blocks opening** when the mandatory scan is incomplete;
  it does not call an unscannable document clean.

## Definition freshness is not detection completeness

The installed scanner requires a successful signature-database check within
**48 hours**, including on clean-cache hits. Missing, stale, incomplete, or
unverifiable definitions **block** managed opening. This freshness gate limits
how old the *last successful check* can be; it cannot prove that every possible
malware family has a signature, that definitions caught a new threat, or that
the engine is free of detection gaps.

The existing **90-day SHA-256 clean-scan cache** is a separate trade-off:
unchanged content that previously passed the matching scan policy may reuse
its verified clean result without another ClamAV scan. Even after newer
definitions are installed, a previously cached clean document is **not
automatically rescanned** solely because signatures changed. The mandatory
48-hour freshness, file-integrity, quarantine, and verified-destination checks
still apply on each managed open. See the [main README](../../README.md) for
the documented way to force a new scan by clearing the cache while the opener
is not running; do not alter scanner flags or disable safeguards.

## What to do with a result

Treat **detected malware** as a block; do not bypass the scan, strip macOS
quarantine, or change destination applications to evade it. For missing or
outdated definitions, run the normal signature updater and retry only after
the required checks succeed. Treat a clean result as limited evidence, not
authorization to trust suspicious PDF links, attachments, or requests for
credentials. Keep the PDF viewer and macOS protections up to date.

PDF Magic Opener preserves macOS File Quarantine; Gatekeeper and XProtect
remain separate defenses. This gate applies only to files actually routed
through the opener, **not** every PDF loaded by every browser or application.
See [macOS security controls](../macos-security-controls.md) and
[what Standard checks](../protection/standard-checks.md) for the enforced
Built-in baseline and the preview-only protection levels.

This document changes **no** scan settings, signatures, cache policy,
quarantine handling, or user-selected PDF application.
