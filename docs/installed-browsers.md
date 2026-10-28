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

## Firefox and Chromium installed together (opener-0156)

The macOS CI job compiles `discover-installed-browsers.swift` with
`test-firefox-chromium-discovery.swift` and constructs **Firefox.app**
(`org.mozilla.firefox`) and **Chromium.app** (`org.chromium.Chromium`)
in separate disposable system-style and user-style Applications folders.
The test verifies that both are discovered at once under distinct identifiers
and correct paths, regardless of duplicate discovery inputs, with stable
ordering and valid JSON output. Unrelated applications with browser-like names
must not appear.

It then removes Firefox and Chromium in turn to confirm the surviving browser
is retained independently; it also checks that a nonexecutable bundle is
excluded and no application executable is launched. The fixtures do not install
real browsers, register apps with macOS, change saved PDF targets, or test PDF
rendering. Scanner and quarantine behavior remain unchanged.
