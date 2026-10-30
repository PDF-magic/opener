# Display incomplete downloaded-PDF scans (opener-0698)

An incomplete scan is a **blocked result**, not a clean or malware
detection. The canonical native status is exactly \`incompleteScan\`
(defined in \`scan_results.py\`); the installed native response contract
also mandates \`DENY_OPEN\`, preserved quarantine, and an attention alert.
This change adds an **opt-in, extension-owned** presentation boundary
without weakening the installed scan gate or changing user notifications.

\`createDownloadIncompleteScanDisplay(root, coordinator)\` returns
\`{ show(scanRequestId), clear(), dispose() }\`. It expects an
extension-owned DOM element and a separately authenticated, verified native
coordinator with the own property \`nativeScanResultsReady: true\` and
the async method \`readVerifiedDownloadScanReport(scanRequestId)\`.
That flag **does not prove authentication**. The trusted integration must
independently verify host identity, request correlation, final scan evidence,
filesystem identity and applicable ClamAV/freshness and quarantine gates.

The response must be exactly \`{scanRequestId, report}\`, with a
path-free \`CombinedScanReport.to_dict()\` schema-v1 report from the
trusted native scanner:
- \`authorizesOpen: false\` and \`requiresBlock: true\`
- \`scan.status: "incompleteScan"\`
- \`clamav.effectivePolicyId: "built-in"\` and a bounded, unique array of
  validated ClamAV signature identifiers
- A distinct native \`structuralFindings\` evidence object

Valid signature names are deliberately **not presented as a complete
malware conclusion** when the scan is incomplete; a partial scan cannot
establish a complete verdict. Malformed, forged, uncorrelated, accessor-
backed, unknown, or non-incomplete status values fail closed and never
show the incomplete-scan warning. Native exceptions and diagnostics are
never rendered. A completed \`scan.request\` acknowledgment alone is
never sufficient evidence for display.

Only on a canonical, correlated incomplete report does \`show()\`
display an accessible \`role="alert"\` warning:

> Scan incomplete — opening stopped
>
> The required safety scan did not finish. This PDF cannot be opened
> until the scan completes successfully.

These strings are fixed; no file paths, URLs, raw native errors, user
content, signatures or untrusted report fields enter the DOM. The result
is an immutable \`{status:"displayed", incompleteScan:true,
authorizesOpen:false}\`. Otherwise the element stays hidden and the
fixed immutable \`unavailable\` result has \`authorizesOpen:false\`.
\`clear()\` and \`dispose()\` invalidate pending asynchronous reports
and prevent old results from restoring an outdated warning. A subsequent
different status removes a prior incomplete-scan notice.

The currently installed WebExtension background remains intentionally
inactive and the standalone native messaging host still reports
\`trusted-scan-coordinator-required\`. **Production activation awaits
a separately authenticated native scanner coordinator.** This task
does not enable scanning or browser listeners, request new permissions,
alter the browser manifest, disable native error alerts, or modify
scanner/quarantine/selected-app behavior or user notification settings.

The 13 regression tests in
\`extensions/webextension/tests/download-incomplete-display.test.mjs\`
run automatically through the existing WebExtensions \`npm test\` step in
GitHub's \`scanner-tests\` job. They cover exact status gating, safe
presentation, malformed reports, request identity, native failures,
revocation of coordinator readiness, stale results, and inert startup.
