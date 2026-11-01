# Developer ID notarization and stapling (opener-1145)

PDF Magic Opener's **native macOS preferences application** must be signed
using Developer ID, use the hardened runtime, and pass Apple's notarization
service before a public outside-the-Mac-App-Store release. **This is a
credentialed release procedure, not a claim that current unsigned CI builds
have been notarized.** This does not authorize unsigned browser extensions
or bypass the application's existing PDF scan gate.

## Prerequisites

1. Obtain the reviewed signed `PDFMagicOpener.app` from the separate Developer ID
   signing and build work (opener-1137, opener-1138, opener-1140). Its bundle ID
   must be `local.studio.pdfmagicopener.swiftui` and all native helper executables
   must be signed. Ad-hoc signatures are not acceptable.
2. Create `PDFMagicOpener-signed.zip` with `ditto -c -k --keepParent` **after**
   signing. Publish it as the single-file `signed-macos-app` GitHub Actions
   artifact from a **successful run of the exact current main SHA**.
   Reproducible release and archive tasks provide this upstream artifact.
   This task does not build, sign, or generate disk images.
3. An authorized operator must configure GitHub's protected
   `macos-notarization` environment and its encrypted `NOTARY_APPLE_ID`,
   `NOTARY_APP_PASSWORD` (Apple app-specific password), and `NOTARY_TEAM_ID`
   secrets. Apply environment approval restrictions. Never commit or print
   credentials, certificates, API keys, or keychain files.

Run **Notarize signed macOS application** manually from `main` and pass the
successful signed-artifact workflow run ID. The job refuses other branches or
repositories, verifies that the producing run succeeded at the exact current
main commit, and downloads the named signed artifact. An absent prerequisite
or credential prevents submission.

The script rejects unsafe archive paths, invalid helper bundles, wrong app
identity, missing Developer ID authority, a mismatched Team ID, and missing
hardened runtime. It verifies bundled helper signatures, calls
`xcrun notarytool submit --wait`, and requires `Accepted` from both submission
and an independent `notarytool info`. It then staples the extracted app,
validates the ticket with `xcrun stapler validate`, rechecks code signatures,
and runs `spctl --assess --type execute`. Only after all checks pass does it
repackage the stapled app using `ditto` and publish `notarized-macos-app`.

A ZIP itself cannot be stapled: the **application inside** is stapled before
the distributable ZIP is created. A separately distributed DMG must undergo
its own notarization and stapling verification in the separate archive task.

Verify the resulting stapled app on a clean supported macOS machine before
distribution. This workflow does not publish a GitHub Release, change
installations, access user preferences or scanner signatures, or allow scan
bypasses. Rejected submissions, failed checks, missing credentials, invalid
tickets, and unexpected signatures produce **no release artifact**.

Authorized local operators may also run `scripts/notarize_release.py` with
`--signed-zip` and `--output-zip` while supplying the three `NOTARY_*` variables
out-of-band. Tests mock Apple tools and perform no real submissions.
