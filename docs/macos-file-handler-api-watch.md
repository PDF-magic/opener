# macOS file-handler API watch (opener-1167)

This is the maintenance register for the native macOS APIs used by PDF Magic
Opener to discover PDF handlers, check target applications, set the *opt-in*
PDF default and launch files **only after** the existing scanner gate approves
them. It is not a second implementation of Launch Services or an automatic
handler migration.

## What is monitored

| Surface | Production examples | Compatibility risk |
| --- | --- | --- |
| `NSWorkspace` application discovery | `verify-pdf-target.swift`, `launch-scanned-file.swift` | Installed destination lookup or registered PDF-capability results change |
| `NSWorkspace.OpenConfiguration`, `open(_:withApplicationAt:configuration:completionHandler:)`, `openApplication(at:configuration:completionHandler:)` and `open(_:)` | `launch-scanned-file.swift` | Completion, launch and fail-closed semantics drift |
| `NSWorkspace.setDefaultApplication(at:toOpen:completion:)` | `make-pdf-magic-default.swift`, `set-pdf-default-handler.swift`, `pdf-handler-history.swift` | User consent, callback or default-handler registration behavior changes |
| `UTType.pdf` and `LSCopyDefaultRoleHandlerForContentType` | `identify-pdf-handler.swift`, `pdf-handler-history.swift`, `set-pdf-default-handler.swift` | PDF UTI identity, Launch Services readback or API deprecation changes |

The [inventory regression](../tests/general/macos-file-handler-api-watch.py)
ensures monitored call sites remain recognizable and the
[Swift API probe](../scripts/macos-file-handler-api-probe.swift) references all
of these SDK entry points. On every PR, merge-group run and `main` push,
the [read-only macOS workflow](../.github/workflows/macos-file-handler-api-watch.yml)
type-checks that probe with `-warnings-as-errors` using the current
`macos-latest` runner SDK, recording the installed macOS, Xcode and SDK
versions in the Actions job summary. It also runs **weekly on Monday at
09:17 UTC**, or via **manual** dispatch after an Apple announcement.

The probe's function is **not executed**: type-checking does not open a
document, change the user's default handler, register applications, access
their settings, or launch any installed browser. SDK compile failures,
missing APIs, deprecation warnings and changed project call sites surface as
failing checks. Enable repository GitHub Actions failure notifications so
scheduled failures reach maintainers; green PR checks do not mean Apple's
upstream release notes were reviewed.

## Apple primary sources and review procedure

Review at least monthly and following a new macOS or Xcode beta/stable SDK:

- [AppKit NSWorkspace](https://developer.apple.com/documentation/appkit/nsworkspace)
  for default-app consent, app discovery and launch completion semantics.
- [Uniform Type Identifiers](https://developer.apple.com/documentation/uniformtypeidentifiers)
  for `UTType.pdf`.
- [Launch Services](https://developer.apple.com/documentation/coreservices/launch_services)
  for default-handler readback and any deprecations or replacement interfaces.
- [Xcode release notes](https://developer.apple.com/documentation/xcode-release-notes)
  and [macOS release notes](https://developer.apple.com/documentation/macos-release-notes)
  for new SDK availability, behavior changes and regressions.

Compare Apple changes to the exact production call sites in the table, check
whether the supported deployment target or runner SDK has changed, and
record the reviewed Apple OS/SDK versions, links, expected impact, maintainer
and next action in the normal maintenance issue/PR. A new Apple release by
itself is **not** proof of a breaking API change. New or removed call sites
must update the inventory and probe together in a reviewed PR.

For a reported regression, reproduce on a disposable Mac/user profile with
the real existing default-handler, Finder-open, selected-browser and
quarantine/scanner tests, including user-denied consent and failed launches.
Do **not** test by changing an actual user's file associations. Keep the
mandatory scan-before-open path, fail-closed behavior, quarantine, explicit
handler consent, the user's chosen destination and other user preferences
unchanged. Migrations and API replacements require separately reviewed
implementation changes, compatibility tests and a safe rollback; no SDK
watch action silently rewrites preferences or upgrades the installed app.

This watch checks compilation on GitHub's current stable hosted macOS runner.
It does **not** monitor every Apple beta, prove Launch Services runtime
behavior on each supported macOS release, or detect every undocumented
behavioral change. Existing native integration tests and manual release-note
review remain necessary.

Run the deterministic, network-free inventory regression locally with:

```sh
PYTHONPATH=. python3 tests/general/macos-file-handler-api-watch.py -v
```

On macOS with Xcode Command Line Tools, type-check (but **not execute**) with:

```sh
xcrun swiftc -typecheck -warnings-as-errors scripts/macos-file-handler-api-probe.swift
```
