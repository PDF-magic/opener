# Safari-downloaded PDF managed opening test (opener-0821)

The **Safari downloaded PDF managed opening** macOS GitHub Actions check
launches real Safari through Apple's SafariDriver, confined to an isolated
automation window on a disposable runner. A loopback-only HTTP server serves
an in-memory, one-page PDF through a link and
`Content-Disposition: attachment`. The test clicks that link using
WebDriver and requires Safari's browser request, the expected unique
filename saved by Safari under the runner's Downloads directory, and the
**exact completed PDF bytes**. It does not synthesize a download by
copying from the server, and fails if Safari does not write the file.

The test next passes **that same downloaded file** to the existing
`scan-and-open.py` policy, with a strictly mocked ClamAV subprocess,
verified-application check and final native application launch. It asserts:

- A clean scan permits the selected Safari destination only **after** the
  complete scan, followed by a correctly scoped clean-cache hit.
- A simulated malware detection and a scanner failure block all opening
  and do not reuse another test case's cached clean verdict.
- Existing `com.apple.quarantine` bytes survive clean, cached, blocked
  and failed scans. If loopback Safari does not tag its download, the
  test attaches an explicit synthetic quarantine marker **only on the
  disposable downloaded fixture**. That is not evidence Safari originally
  applied the tag.
- All successful handoffs record the original-document origin. The
  downloaded PDF's bytes are unchanged and the browser preference remains
  `com.apple.Safari` only inside an isolated mock.

The native-launch operation is **recorded, never executed**: the test does
not actually open the downloaded PDF with a second application, grant
Gatekeeper approval, run production ClamAV, install a browser extension,
configure Safari download preferences, or claim control over Safari's own
automatic-opening settings. The real native launcher and scanner safety
are covered by the repository's separate existing suites. No user
preferences or existing downloaded documents are accessed; the macOS
runner test creates and removes only a UUID-named disposable PDF.

The portable `--self-test` verifies HTTP download headers, strict
404 response, synthetic scanner outcomes and preservation contracts,
but **does not claim to have exercised real Safari**. Both that test and
the browser-specific source contract run in scanner CI; the `--live`
check must pass separately on macOS. This test is independent of
[Safari's inline PDF viewer test](browser-pdf-viewers.md) and
[general quarantine retention](macos-quarantine-removal-inventory.md).
