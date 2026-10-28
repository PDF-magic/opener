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

## Safari-only discovery regression (opener-0154)

The macOS CI suite runs `test-safari-only-discovery.swift` against the existing read-only browser discovery function. In a disposable application directory, only a synthetic `Safari.app` with bundle ID `com.apple.Safari` qualifies as a browser; non-browser apps and an unrelated app using a Safari-like name are excluded. The test checks stable, single-entry discovery, JSON inventory compatibility, rejection of an unexecutable or removed Safari bundle, and that discovery never runs an app executable. It supplies no registered applications and does not alter actual macOS browser installations, default handlers, or user preferences. This tests discovery rather than Safari PDF rendering or signing.
