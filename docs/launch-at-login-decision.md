# Launch at Login decision (opener-0199)

**Decision: do not add a Launch at Login option at present.** It is
conditional on a genuine background requirement, which the standalone
macOS preferences application does not have.

## Architecture

- The SwiftUI application (`local.studio.pdfmagicopener.swiftui`) displays
  settings, information, and explicit, user-triggered controls. It does not
  register to open PDFs and does not manage long-running scans.
- The separately installed PDF handler (`local.studio.brave-pdf-opener`)
  registers with Launch Services for `com.adobe.pdf`. macOS launches it
  when a PDF is opened, regardless of whether the preferences app is running.
  The installed handler owns ClamAV scanning, verification, cancellation,
  and opening verified documents.
- The installer already registers a **separate**, scheduled LaunchAgent
  (`local.studio.pdf-malware-signatures`) for updating malware signatures.
  Its `RunAtLoad` behavior is **not** a login item for the SwiftUI app;
  do not remove or disable that updater to enforce this policy.
- Automatically launching the windowed preferences app at sign-in would add
  a redundant process or unexpectedly show a settings window. It could also
  incorrectly suggest that the PDF scanner stops working when Settings quits.

## Implementation boundary

Keep the regular windowed preferences app, its Dock presence, the existing
Settings and Quit commands, and the separate installed PDF handler. Do not
register the preferences app with `SMAppService`, create a login-item target,
install a LaunchAgent for the preferences app, or expose a misleading
Launch at Login toggle. No login-at-startup preference or migration is needed
under the current architecture.

This decision does not affect the user's chosen PDF browser, macOS PDF
associations, malware-signature update schedule, scan gating, or quarantine
handling. A focused CI check guards the independence of these components.

## When to reconsider

Add an explicitly opt-in Launch at Login control only if a future approved
feature genuinely requires the **preferences application** to run continuously,
such as user-visible monitoring that cannot be performed by the installed
handler. Such a change needs accessible status and disable controls, documented
login-item registration and recovery, and dedicated macOS lifecycle tests.
