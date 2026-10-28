# Menu-bar status item decision (opener-0176)

**Decision: not enabled.** The standalone PDF Magic Opener SwiftUI
application is a normal, windowed preferences application. A persistent macOS
menu-bar status item is **not necessary** for its current responsibilities.

## Why no status item

- The standalone app exposes preferences through its existing main window,
  including the General, Browsers and Security sections. macOS already
  provides application-menu commands and a standard Quit action.
- Scanning, file verification, quarantine handling, and PDF handoff belong to
  the **separate installed AppKit/ClamAV handler**. They keep working when
  the SwiftUI preferences app is not running.
- A menu-bar icon could falsely suggest that the SwiftUI app is required to
  remain open for PDFs to be scanned, or that it provides live scan status.
  It currently does neither.
- Keeping a second always-visible icon or a background-only agent would add
  menu-bar clutter and process lifecycle complexity without useful controls.

## Implementation boundary

Keep the existing window-based `WindowGroup` and ordinary app lifecycle;
**do not** add SwiftUI `MenuBarExtra`, AppKit `NSStatusBar`, or set
`LSUIElement` to turn the app into a background menu-bar agent. There is
therefore no enabled menu-bar status item to implement for this checklist item.
A focused CI test guards against accidental activation and verifies the
standalone window and Quit action remain available.

This decision does **not** disable the installed PDF handler, change any
selected browser or system PDF association, or modify scanning safeguards.

## When to reconsider

Revisit this decision only if the application later owns an actual
long-running background service, persistent scan-progress state, or
user-requested quick actions unavailable through the existing preferences
window. Such a feature should be explicit, accessible, have a clear Quit
control, and undergo separate review and CI coverage.
