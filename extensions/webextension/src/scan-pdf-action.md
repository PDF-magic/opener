# Scan PDF action contract (opener-0578)

The shared WebExtensions module \`src/scan-pdf-action.js\` defines a visible
**Scan PDF** action label and a fail-closed, explicit-click action controller.
Call \`createScanPdfAction()\` without a coordinator to obtain a disabled state;
the current extension has no native scanner connection and cannot scan files.

A future trusted UI can pass a **separately reviewed** coordinator with an
explicit \`manualScanReady: true\` value and a
\`requestUserSelectedPdfScan()\` method. The UI must invoke
\`activate({ userInitiated: true })\` directly from an explicit click, after
separately verifying the interaction. The coordinator is responsible for
selecting and safely accessing the user's intended local PDF, checking the
native scanner and enforcing ClamAV signature freshness, file integrity,
quarantine and selected PDF application policies.

This module deliberately passes **no browser URL, filename, file bytes or
claimed verdict** to the coordinator. A successful acknowledgment means only
\`request-submitted\`; it is never proof that the scan completed, that the PDF
is clean, or that opening is permitted. Errors return generic, path-free
\`unavailable\` results. Merely setting configuration defaults, detecting a
PDF candidate or observing a browser download cannot enable native scanning.

The browser toolbar popup belongs to opener-0577's independent PR #371,
stacked on opener-0576's PR #369. That popup currently has no scanner bridge;
a real \`Scan PDF\` control must remain disabled until a trustworthy, reviewed
native request path is connected. This action module does not alter manifest
permissions, turn on downloads listeners, install a native host or open PDFs.

The existing WebExtensions \`npm test\` job runs
\`tests/scan-pdf-action.test.mjs\` automatically. Tests verify manual consent,
injection requirements, no implicit monitoring, safe acknowledgments, path-free
errors and absence of native or browser side effects.
