# Browser-native PDF download handling — real-browser verification (opener-0811)

The dedicated [browser-native download CI workflow](../.github/workflows/browser-native-pdf-downloads.yml)
tests actual **Chrome for Testing and Mozilla Firefox download managers**.
The earlier simulated [automatic-opening regressions](download-automatic-browser-opening-test.md)
do not demonstrate an installed browser writing a downloaded file.

Each test uses a fresh, disposable headless browser profile and a private
temporary downloads directory. A controlled HTTP server bound exclusively to
`127.0.0.1` serves the same independently generated, valid one-page PDF via
two routes:

- `/native-download/attachment.pdf`: `Content-Type: application/pdf` with
  `Content-Disposition: attachment; filename="pdfmagic-attachment.pdf"`.
- `/native-download/octet`: `Content-Type: application/octet-stream` with
  `Content-Disposition: attachment; filename="pdfmagic-octet.pdf"`.

Both responses use exact `Content-Length`, `no-store` caching and `nosniff`.
The [fixture](../extensions/webextension/scripts/native-pdf-download-fixture.mjs)
also rejects unknown paths and non-GET requests.

## Browser assertions

**Chrome:** An isolated Chrome for Testing process uses the browser's
`Browser.setDownloadBehavior` DevTools endpoint to enable downloads **only**
in its disposable test directory. For each real HTTP PDF navigation, the
test requires a corresponding `Browser.downloadWillBegin` event with the
expected URL and suggested filename, a matching
`Browser.downloadProgress: completed` event, the correct received byte
count, and exactly the original PDF bytes saved at the expected filename.

**Firefox:** An isolated Firefox profile is explicitly configured to save
PDF and octet-stream responses to its disposable directory. Its built-in
inline PDF.js handling is disabled **only within this throwaway test profile**
so that the test exercises the browser's download path. WebDriver performs
actual link clicks, then the test verifies the HTTP request, complete PDF
bytes on disk, and expected filenames with no pending `.part` transfer.

Both require only the two expected files in the temporary download folder.
The browser processes, HTTP listeners and temporary profiles are cleaned up
at the end. A separate [Node regression suite](../extensions/webextension/tests/browser-native-pdf-download.test.mjs)
checks the server responses, PDF validity, CI wiring and scanner isolation;
the existing WebExtensions `npm test` runs it through `scanner-tests`.

## Safety and scope

These tests verify **browser-owned download behavior** for two local HTTP
response types, not the PDF Magic extension's ability to prevent downloads,
block auto-opening, scan downloaded files, override external app choices,
or control downloads in untested browsers. They neither install the extension
nor request `downloads`, `downloads.open` or `nativeMessaging` privileges.
The browser's native download manager is different from the operating system's
associated PDF application, which is never launched by this test. Actual
automatic opening preferences and interception guarantees require separate,
explicit testing.

No real websites, accounts, external URLs, private user PDFs, production
browser settings, scanner binaries or quarantine controls are touched.
The shipped extension's inert background and existing safe-open policy remain
unchanged.
