# Display structural warnings after completed-download scans (opener-0697)

`createDownloadStructuralWarningsDisplay(root, coordinator)` creates an
opt-in accessible warning display for a trusted native scanner coordinator.
The caller supplies a dedicated extension-owned DOM element, establishes
the coordinator's authentication independently, and explicitly calls
`show(scanRequestId)`. A readiness flag is not authentication.

The renderer requires a correlated `{ scanRequestId, report }` response
containing the existing path-free `CombinedScanReport.to_dict()` schema-v1
envelope and explainable `structuralFindings` schema-v2 report.
Only fixed, locally authored stage/code/severity labels are displayed.
Unfinished or missing stages and findings requiring review, blocking or
incomplete inspection are warnings; informational-only evidence is not
displayed as a warning. The module validates **all** stage records and
every finding before rendering, including entries beyond its 64-row limit.
An inconsistent `requiresBlock`, malformed result/next action, unknown
code, unsupported effective policy or conflicting scan status fails closed.

The view uses `textContent` and accessible `role="alert"`, never
`innerHTML`, arbitrary finding explanations, filenames, URLs, PDF object
contents, raw scanner diagnostics or metadata from download events.
A report with no structural warnings leaves the view hidden; **absence of
warnings is not a clean scan verdict**. Clearing, disposing, losing native
readiness or receiving an invalid/stale response cannot leave a misleading
warning visible. A positive display result has `authorizesOpen: false`.
Other malware and clean-result presentation components have separate scope.

**Deployment prerequisite:** The shipping WebExtension remains inactive, and
the standalone native host does not run native scanner jobs. A separately
implemented trusted coordinator must generate authenticated, correlated
combined reports before this renderer can display live warnings. This PR
does not activate native messaging, browser monitoring, scanner analysis,
Enhanced/Maximum protection, quarantine removal or opening. The existing
ClamAV signature freshness, file integrity and fail-closed scan gates and
all user customizations remain untouched.

The focused Node tests in
`tests/download-structural-warnings.test.mjs` run automatically under
WebExtensions `npm test` in the required `scanner-tests` CI job.
