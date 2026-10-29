# Test dragging a PDF onto PDF Magic Opener

Dragging a PDF onto the **PDF Magic Opener** app icon explicitly targets that
app even when a different program is the default PDF handler. This differs
from double-clicking or choosing Finder's **Open** command.

## Manual Finder or Dock gesture

1. On a macOS desktop with PDF Magic Opener installed, record the macOS
   version, current default PDF handler and selected post-scan app. Do not
   change either selection for this test.
2. Use a harmless local PDF, ideally with spaces or Unicode in the filename.
   Avoid private documents and keep the PDF in its original directory.
3. In Finder, physically drag that PDF onto **PDF Magic Opener.app** in
   Applications or onto its Dock icon, then release the mouse or trackpad.
   Do not drop it onto the browser or use Finder's Open command.
4. Confirm the same PDF reaches the opener, the scan progress is shown, and
   the destination PDF viewer does not open until an approved scan. Confirm
   an approved file opens in the previously selected viewer. If a safe
   blocked-scan or cancellation fixture is available, confirm no opening
   or quarantine removal occurs after rejection or cancellation.
5. Confirm the default PDF handler and selected browser were not changed.
   Record the observed result and PASS/FAIL without document contents,
   private paths, secrets or sensitive logs.

This literal pointer gesture requires an interactive Finder desktop.
GitHub-hosted CI cannot claim to have performed the physical drag.

## Automated macOS CI companion

Run: python3 test-pdf-drag-drop.py

The integration test builds a disposable copy of the real native opener,
replaces only its scanner command with a local receipt stub, and sends the
PDF to that specific app via NSWorkspace (the explicit-application Launch
Services path used by dropping a document onto an app icon). It verifies
that the native open-documents delegate reaches the scan gate with the same
PDF identity and that the system default PDF handler stays unchanged.

This does not simulate the pointer gesture or establish ClamAV's live
verdict. Existing scanner, cancellation, quarantine and destination tests
cover those decisions. The test neither installs a default handler nor
changes user preferences or accesses non-test documents.
