# When inconclusive Enhanced analysis blocks opening (opener-0302)

`enhanced_inconclusive_results.assess_inconclusive_opening(report)` is a
**passive, fail-closed policy decision** over the validated
[structured findings contract](../structured-enhanced-findings.md).
It does not inspect documents, run a scanner, change a saved preference,
remove quarantine, or authorize opening.

The report's `expected_stages` must come from **trusted policy**, not the PDF.
**Opening is blocked** if any expected stage was not run, any expected stage
is marked incomplete (even with no findings), or any reported finding leaves
safety evidence unresolved. This includes malformed or conflicting structures,
unresolved references, active content, suspicious embedded URLs, unexpected
embedded files, unsupported features, resource limits, and inspection failures.
A low, informational producer-assigned severity never overrides one of these
reasons. Suspicious or critical incremental revisions also block, but a
routine *informational* revision is not automatically inconclusive.

This rule preserves **all** prior `requires_block` decisions from the
[structured report](../structured-enhanced-findings.md) and
[explanations](finding-explanations.md); it cannot downgrade them.
The policy explicitly distinguishes `blocksForInconclusive` from the
aggregate `requiresBlock`. The output decision is either `block` or
`noDecision`, **never** `allow` or `clean`. Even when no inconclusive
reason was found, `authorizesOpen` is always `false`; the caller must
independently establish every mandatory baseline and Enhanced condition.

Each reason carries only the validated stage identifier, a fixed reason code,
and optional bounded object/page numbers. The immutable policy output is
serialized in deterministic expected-stage order and excludes PDF-supplied
paths, scripts, form data, URLs, exception text, and filenames. It cannot be
overridden by caller-supplied raw JSON or by a user setting.

This is distinct from the *follow-up inspection planning* in
[opener-0301 PR #198](https://github.com/PDF-magic/opener/pull/198):
that task defines **which checks to perform**; this task defines when
existing evidence is **insufficient to proceed**. Neither claims that the
additional checks ran or permits a subsequent scan/open shortcut.
Enhanced remains non-selectable. The deployed Built-in ClamAV scan, cache,
signature freshness, file-integrity gate, quarantine, and application handoff
continue unchanged.
