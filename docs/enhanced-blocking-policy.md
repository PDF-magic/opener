# Explicit Enhanced finding blocking policy (opener-0300)

`enhanced_blocking_policy.determine_blocking_findings(report)` classifies
*validated, structured* Enhanced PDF findings into three dispositions. It
is separate from [inconclusive-evidence enforcement](enhanced-inconclusive-results.md),
[follow-up inspection planning](enhanced-additional-inspections.md), and
[human-readable explanations](enhanced-finding-explanations.md). This policy
does not inspect bytes, execute actions, run a scanner, or authorize opening.

| Finding code | Minimum disposition | Why |
| --- | --- | --- |
| `malformedStructure` | `denyOpening` | Structure cannot be trusted |
| `conflictingStructure` | `denyOpening` | Competing interpretations are unsafe |
| `unresolvedReference` | `denyOpening` | Required object cannot be verified |
| `activeContent` | `holdForReview` | Capability must be inspected without execution |
| `suspiciousUrl` | `holdForReview` | Destination cannot be trusted without review |
| `unexpectedEmbeddedFile` | `holdForReview` | Embedded content needs independent inspection |
| `incrementalRevision` | `observation` | An ordinary informational revision is not inherently unsafe |
| `unsupportedFeature` | `denyOpening` | Required feature validation is unavailable |
| `resourceLimit` | `denyOpening` | Required safety evidence could not be completed |
| `inspectionFailure` | `denyOpening` | Inspection did not establish reliable evidence |

Both **`holdForReview` and `denyOpening` require blocking now**. A hold
means additional review may eventually resolve the finding under a *separate,
trusted execution policy*; it is not permission to ignore the risk, execute PDF
content, or bypass ClamAV. Explicit `blocking` severity signals that opening
must stop, and critical severity also upgrades a finding to `denyOpening`.
Review-required and suspicious severities upgrade `observation` to
`holdForReview`; severity can never lower a code's minimum disposition. Thus a
critical or blocking revision blocks, a review-required or suspicious revision
requires review, and an informational revision alone is merely recorded.

All expected stages must be declared by trusted policy, not by the PDF.
Missing or incomplete stages require blocking even with no findings. The
aggregate decision also retains **every blocking signal** from the structured
report, the earlier inconclusive assessment and follow-up inspection plan.
It never converts a failure or an incomplete inspection to a pass. Adding a
new `FindingCode` requires explicitly updating the exhaustive rule table;
there is no permissive default.

Decisions are immutable and preserve every finding (including duplicates)
in expected-stage order, with typed code, severity and bounded object/page
references. Serialization exposes only fixed identifiers, bools and safe
numbers, never document-controlled strings, URLs, paths or exception messages.
A false `requiresBlock` is **not** a clean verdict: `authorizesOpen`
is always false, including for an empty report or routine revision.

The dedicated CI workflow tests all ten finding codes at all five severity
levels, incomplete/missing stages, existing policy monotonicity, data
immutability and privacy, and scanner isolation. Existing Built-in ClamAV,
quarantine, cache, signature freshness, file-integrity checks, PDF handoff,
preferences and non-selectable Enhanced protection are unchanged.
