# Test Browser Integration (opener-0735)

**Browsers → Browser integration test → Test Browser Integration** is a
user-initiated, read-only local diagnostic. It enumerates the same nine
supported browser bundle IDs as the existing browser-preference catalogue and
uses the application's validated installed-browser discovery. It reports the
number of supported browsers detected.

**A result of “Integration test unavailable” is expected today.** The shared
browser extension has no authenticated connection to a live native download
scanner. A successful application discovery is not a successful extension
handshake, an authorization for download monitoring, or an enforced
scan-before-open workflow. This action does not and cannot test an actual
browser download until a separately reviewed and authenticated integration
is available.

Pressing the button does not save or change user preferences, request
permissions, launch browsers or downloads, contact a native host, run the
scanner, alter malware warnings, or authorize opening files. It reports no
success state based on the “Enable Browser Download Monitoring” preference.

Regression coverage: `tests/general/browser-integration-test.py` verifies
that the action is explicit and accessibility-labeled, remains isolated from
native scanning and permissions, and has CI coverage.
`test-browser-integration.swift` verifies the compiled diagnostic model
for absent, partial and complete discovery and proves that a saved opt-in
cannot turn an unavailable integration into a success.
