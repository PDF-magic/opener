# Installation prerequisite reporting (opener-0961)

Running `install-allow-and-open.sh` checks basic requirements before modifying
any installed application, workflow, signature database, preference, or migration
journal. The check reports **each missing prerequisite** with a fixed, actionable
message and exits nonzero. It never prints local paths, raw command errors, PDF
contents, private settings, or scanner output.

The preflight checks macOS 13+, the existing **Allow and Open** Finder Quick
Action, macOS `xcrun`, `swift`, `codesign`, `launchctl`, and availability of
the Swift compiler. An unavailable Swift compiler directs the user to run
`xcode-select --install`. A missing `python3` command is diagnosed by the
installer's shell before the Python reporter starts.

If ClamAV is already installed at a supported location, Homebrew is not
required. If ClamAV is missing but Homebrew is available, the reporter describes
the upcoming package provisioning as a **notice**, not as a completed install.
If neither is available, it explains that the user must install Homebrew or a
supported ClamAV scanner. Homebrew availability is determined using the existing
read-only detector from opener-0954, not a second competing implementation.

This is **diagnostics only**: it neither installs packages nor grants permission
for an installation operation. Existing package-install authorization and
Homebrew handling remain independent. A passing preflight does not certify
ClamAV version, malware signatures, safety, quarantine handling, PDF defaults,
or the success of any later installation operation; all existing scanner
fail-closed checks remain in place.
