# Open PDF Magic Preferences action — opener-0577

The shared browser toolbar popup contains one user-initiated link labeled
**Open PDF Magic Preferences**. Selecting it requests
`pdfmagicopener://preferences`, a local URL handled by the installed macOS
PDF Magic Opener preferences application. The browser may ask for confirmation.
If the native app is missing or the user declines, the extension does not
claim success or bypass that decision.

The native application accepts **only that complete URL** and raises its
existing preferences window. It never interprets URL parameters as PDF paths,
starts a scanner, changes a PDF default handler or modifies preferences.
The host app continues to have no PDF document association.

The popup remains **Not active** for PDF scanning and opening. This local
link is not browser-to-native messaging, a ClamAV verdict, browser permission,
or permission to open a document. The shared popup has no JavaScript, forms,
remote URLs, document data, or background listeners. Chromium, Firefox and
Safari use the same validated static popup assets; Safari includes them in
the pre-existing app extension's Resources directory.

CI verifies the macOS registered URL scheme and the actual built Safari
popup bytes, and Node tests reject additional or unsafe popup links.
