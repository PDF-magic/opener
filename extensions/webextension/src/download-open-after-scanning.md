# Open After Scanning action (opener-0704)

\`createDownloadOpenAfterScanningAction(root, coordinator)\` offers an explicit
**Open After Scanning** button for an extension-owned UI associated with a
native scan request. This opt-in, side-effect-free module is not installed
in the currently inactive popup or background. It does **not** scan or
open a file itself.

## Trusted native integration required

A separately authenticated native scanner coordinator must supply:
- An own data property \`nativeOpenAfterScanningReady: true\`.
- An async \`requestOpenAfterScanning({ scanRequestId })\` method that
  atomically associates the user's intention with the exact trusted
  native scan session and returns \`{ accepted: true }\` only if the
  request was **queued**, not if a scan was clean or a file was opened.

A boolean readiness flag is not authentication. The trusted integration
must establish native host identity and correlate its scan request ID to
the currently owned PDF download before offering the action. Native code
must independently enforce all scan gate prerequisites and *revalidate*
file existence, canonical identity, content integrity, ClamAV signature
freshness, a complete clean scan, quarantine retention and the user's
selected application **at final handoff**, including after any clean-cache
reuse or asynchronous race. Incomplete, malicious, interrupted, timed-out
and failed scans must never trigger an opening. No browser metadata,
untrusted "clean" flags, arbitrary file paths or guessed destination apps
may substitute for those gates.

The shared extension has no active authenticated coordinator: the
standalone native messaging host deliberately replies
\`trusted-scan-coordinator-required\`, and \`background.js\` remains inert.
Consequently this task adds the **action contract and accessible
interface**, not an operable live download-opening control. It does not
make the built-in popup's disabled manual Scan PDF button active, add
permissions, edit the manifest, alter scanner/quarantine logic, or
modify existing user preferences.

## User-visible behavior

An explicitly configured trusted UI calls \`offer(scanRequestId)\` after
identifying its own scan session. A bounded ASCII request ID and available
coordinator are required. Only then does the extension-owned DOM element
display an actual button labeled **Open After Scanning**, with help text
clarifying that native safety checks must succeed before opening.

A real user click (including keyboard activation) causes one
\`Object.freeze({ scanRequestId })\` request to the coordinator.
Script-generated clicks do not request native work. The button disables
synchronously before awaiting the native callback, preventing repeated
clicks. A positive \`{ accepted: true }\` acknowledgment displays only
**Open requested. The native scanner must still approve opening.**
Every result continues to have \`scanVerified: false\` and
\`authorizesOpen: false\`. The action never reports success or claims
the PDF was actually launched. Native rejection, missing readiness,
invalid data, synchronous errors, and rejected promises display a fixed
unavailable message without exposing paths or diagnostics.

\`clear()\` and \`dispose()\` remove the button's listener and invalidate
pending results. Changing the scan request replaces the previous button
and prevents its late response from changing the current UI. An already
submitted native request must be cancelled or reconciled by the trusted
coordinator; clearing a browser view does not undo the user's native
request by itself.

## Tests

The 14 regression cases in
\`extensions/webextension/tests/download-open-after-scanning.test.mjs\`
run through the existing WebExtensions \`npm test\` and GitHub
\`scanner-tests\` job. They cover offering/label/accessibility, explicit
user gesture, ID-only submission, synchronous de-duplication,
acknowledgment semantics, missing coordinator, invalid IDs, races,
native rejection/errors, listener cleanup and inert startup.

The installed \`scan-and-open.py\` already owns the scan-before-launch
pipeline. This future browser action may request its normal trusted
processing but **never** bypasses ClamAV, identity, quarantine or the
user-selected PDF application gate.
