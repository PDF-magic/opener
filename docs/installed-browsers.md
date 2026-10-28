# Discover installed macOS browsers

After installing PDF Magic Opener, run:

```sh
"$HOME/Library/Application Support/Studio/allow-and-open/discover-installed-browsers"
```

The read-only command returns a JSON array containing each browser's bundle
identifier and installed application path. It scans `/Applications`,
`~/Applications`, and `~/Library/Applications`, and consults macOS Launch
Services for browsers registered from other locations. These paths are resolved
at invocation time; no catalog is persisted.

For unregistered apps kept elsewhere, explicitly supply a directory or an
individual application bundle:

```sh
"$HOME/Library/Application Support/Studio/allow-and-open/discover-installed-browsers" \
  --search-directory "/Volumes/Apps/Browsers" \
  --application "/Volumes/External/Other Browser.app"
```

The inventory requires a real `.app` directory, a bundle identifier, and an
executable. Known browser identifiers, declared HTTP(S) URL handling, or
Launch Services HTTPS registration identify browser candidates. Duplicate
locations are removed; results are ordered by bundle identifier and path.

**This command never launches an application, opens a PDF, changes macOS
associations, or edits `target-app.txt`.** Listing a browser does not authorize
it to receive a scanned file. The existing PDF-capability checks, signature
exceptions, scanner verification, and explicitly selected application remain
unchanged. To use a custom-location browser for post-scan opening, it must still
be registered with Launch Services under its bundle identifier, satisfy the
existing PDF verification requirements, and be selected using the existing
`target-app.txt` preference.

## Brave-only discovery regression (opener-0153)

The macOS CI suite compiles `discover-installed-browsers.swift` alongside
`test-brave-only-discovery.swift` to exercise discovery with **Brave as the only
browser**. An isolated, disposable `Brave Browser.app` fixture uses the exact
`com.brave.Browser` bundle identifier and an executable. The test confirms
that the resulting inventory contains exactly that browser, remains valid JSON,
does not launch the application, and stops reporting Brave if its executable
becomes unusable. A separate non-browser application is ignored.

This synthetic fixture is deterministic and does **not** claim a real Brave
installation exists on the CI runner or test PDF rendering. The production
scanner, PDF verification, Launch Services registrations and user preferences
are not changed.

## Multiple Chromium-based browser discovery regression (opener-0155)

The macOS CI job compiles `test-multiple-chromium-discovery.swift` with
the existing discovery implementation. It constructs a temporary installation
containing Brave, Google Chrome, Chromium, Microsoft Edge, and Vivaldi across
system, user, and explicitly supplied custom locations. The test verifies
that **all five exact bundle IDs** remain distinct, multiple discovery paths
do not duplicate applications, results are sorted consistently, and inventory
JSON round-trips. A similarly named impostor, a non-browser application, and
a browser without an executable must not enter the inventory.

The test also disables one Chromium executable and checks that only that
installation disappears, with the other browsers unaffected. Synthetic app
executables would record a marker if launched; no marker may appear during
discovery. No real applications, Launch Services registrations, saved PDF
targets, scanner behavior, or quarantine handling are modified. This does
not test actual browser rendering or claim those browsers are installed on CI.
