# Findings requiring additional Enhanced inspection (opener-0301)

`enhanced_additional_inspections.plan_additional_inspections(report)` produces
a passive, immutable follow-up plan for the **validated structured findings**
from [opener-0297](../structured-enhanced-findings.md) and the explainable
results from [opener-0299](finding-explanations.md). It does not run
the checks or change existing results, execute PDF content or permit opening.

Every finding retains its origin stage, diagnostic code, severity and bounded
location, along with a distinct `requiresAdditionalInspection` flag and
`requiredInspections` tuple. The policy is explicit and exhaustive:

| Finding code | Additional inspection or review |
| --- | --- |
| malformedStructure | Validate structure; inspect object relationships |
| conflictingStructure | Inspect object relationships and revision history |
| unresolvedReference | Inspect object relationships |
| knownMaliciousContent | No follow-up; confirmed malicious content remains blocked |
| activeContent | Inspect automatic and other active actions without running them |
| suspiciousUrl | Review embedded URLs without following them |
| unexpectedEmbeddedFile | Inspect embedded files and executable signatures |
| incrementalRevision | Inspect revision history when suspicious or critical; **not** for an ordinary informational revision |
| unsupportedFeature | Review unsupported features; no silent fallback |
| resourceLimit | Review resource limits and retry a failed inspection safely, without increasing limits automatically |
| inspectionFailure | Retry or repair the failed inspection, without treating it as clean |

Known malicious content is terminal blocking evidence, not a request for
another inspection: its follow-up list stays empty, but the separate finding
explanation and blocking policy still deny opening.

The report aggregates required checks in a deterministic, deduplicated order,
but **preserves every finding separately** in the originating expected-stage
order. An expected stage that is missing or incomplete always additionally
requires `retryIncompleteStage`. A completed discovery stage cannot fulfill a
follow-up just because it has the same name; review and actual execution remain
separate contracts. An informational finding that needs further inspection
keeps the plan blocked pending that inspection. Suspicious and critical
findings also retain their existing conservative block decisions.

The serialized output uses `schemaVersion: 1` for this separate
follow-up plan, with `requiresAdditionalInspection`,
`requiredInspections`, `incompleteStages`,
`findingRequirements`, `requiresBlock` and
`authorizesOpen: false`. Fixed identifiers are used throughout;
PDF-supplied paths, URLs, script text, file names, bytes and error messages
are never interpolated.

An empty or completed plan **cannot** mean that a PDF is clean. The existing
Built-in ClamAV gate, signature freshness, quarantine, cache, file integrity,
browser handoff, user preferences and currently non-selectable Enhanced profile
are unchanged. Future production integration must verify that follow-ups
really execute in a bounded, isolated environment, and satisfy all Standard
and Enhanced prerequisites before making any opening decision.
