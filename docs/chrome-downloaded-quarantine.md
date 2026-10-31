# Opening Chrome-downloaded PDFs with macOS quarantine (opener-0822)

This regression verifies a real file downloaded by Chrome can pass PDF Magic
Opener's existing local scanner gate, reach a verified application handoff,
and retain its `com.apple.quarantine` metadata. It also verifies that
scanner malware, error, and timeout outcomes block the handoff and leave the
download untouched.

## Real Chrome download and metadata-preserving handoff

The existing [real Chrome native download smoke](../extensions/webextension/scripts/test-chrome-native-pdf-download.mjs)
retrieves two generated PDFs from an ephemeral `127.0.0.1` server via Chrome
for Testing's actual native download manager. It checks the browser's download
start and completion events, server-supplied names, byte lengths, and exact
saved bytes for both `application/pdf` attachment and
`application/octet-stream` attachment.

Only when `PDF_MAGIC_CHROME_HANDOFF_DIR` is explicitly set to an existing,
empty, non-symlink temporary directory does that test **rename** the two
verified Chrome-produced files into the directory. It refuses an occupied
handoff directory. This uses a same-volume filesystem rename, **not a copy**,
so any Chrome-set extended attributes stay on the original downloaded files.
Without this CI-only option, the existing Linux Chrome/Firefox tests behave
as before and clean up the download profile.

## macOS scanner and opening checks

The dedicated `Chrome macOS downloaded PDF safe-open and quarantine` GitHub
Actions job runs on `macos-15`, launches real Chrome from a disposable profile,
with the sandbox disabled **only** for this synthetic loopback-only CI browser
because the macOS hosted runner denies Chrome's sandboxed Mach-port service.
It then runs
[`tests/general/chrome-downloaded-quarantine.py`](../tests/general/chrome-downloaded-quarantine.py)
against those exact downloaded files. It verifies the PDFs were actually
saved and are still byte-identical.

Headless Chrome may or may not attach a Gatekeeper quarantine marker to a
synthetic loopback HTTP download. The test **preserves the browser's existing
marker if present**; otherwise, it explicitly adds a deterministic test-only
quarantine marker before scanning. This distinction prevents falsely claiming
Chrome always produces quarantine in this headless configuration.

The Python test invokes the real `scan-and-open.py` scan and opening gate,
while substituting an isolated, deterministic scanner verdict and a recorded
launch function. For **each Chrome-downloaded file**, it requires:

- A fresh clean verdict, followed by one verified clean-cache hit, both
  authorizing the configured-target *handoff*, and neither changing PDF bytes
  nor the original quarantine value.
- A malware verdict, scanner process failure, and timeout, each preventing
  the application handoff, retaining the exact quarantine value and leaving
  the downloaded PDF's bytes unchanged.
- The scanner command targeting the **actual Chrome-downloaded local path**,
  the original local-file and integrity checks, and the expected configured
  destination (injected in the test instead of reading user preferences).

No production executable, installed PDF application, ClamAV process, network
service, Finder action, or Launch Services handoff is started by the Python
test. The real `launch_clean_file` function is replaced by an assertion
that a safe handoff **would have occurred only after a complete clean scan**;
it does not assert that a GUI opened or that Gatekeeper's user-facing warning
appeared. A separate interactive macOS GUI test would be needed to prove
those external behaviors.

## Running and safety

GitHub Actions runs the macOS integration in a temporary directory and
always removes it. The shared WebExtension Node regression suite verifies the
handoff contract and the CI wiring. For macOS manual reproduction with a
known Chrome for Testing binary, run the same isolated workflow's two commands
in an empty temporary directory; do not use user downloads.

The tests do not modify the shipped browser extension, scanner policy,
quarantine-removal compatibility hook, installed application, scanner database,
browser defaults, or user preferences. This is solely test coverage for the
previously separate Chrome native-download and macOS quarantine-retention
paths. The main production scan gate remains fail-closed.
