# Clean macOS installation verification (opener-1148)

This is a **fail-closed first-install acceptance gate** for the separately
packaged, Developer ID-signed and Apple-notarized `PDFMagicOpener.app` native
preferences application. It is not an installer for `PDFOpener` (the distinct
PDF scan gate), does not set the system PDF handler, and does not change
ClamAV, browser permissions, scanner signatures or user preferences.

## Automated first installation on a fresh hosted Mac

1. Complete Developer ID signing and Apple's notarization/stapling workflows.
   The upstream `Notarize signed macOS application` workflow must have
   succeeded **at the exact current `main` commit**, and uploaded
   `notarized-macos-app` with `PDFMagicOpener-notarized.zip`.
2. From `main`, dispatch **Clean macOS installation verification** with that
   notarization workflow run ID and the expected ten-character Developer ID
   team identifier. No Apple credentials or signing keys are used by this job.
3. The job refuses any other repository, ref, or untrusted workflow source.
   The isolated GitHub-hosted macOS runner must have **no existing**
   `/Applications/PDFMagicOpener.app`: it will not overwrite an installation.
4. The job checks ZIP paths and contained symlinks, Developer ID signatures,
   expected bundle identity, bundled helper inventory, stapling and
   Gatekeeper **before** installation. It copies that one application into
   `/Applications`, applies a download-like quarantine attribute, repeats
   the signature, stapler and Gatekeeper checks against the installed app,
   then starts the real installed executable with a newly created empty
   synthetic home and confirms it stays running. The runner is disposable,
   and the application is not copied onto the operator's Mac.
5. Record the workflow URL and its success/failure against the exact release
   commit. Any missing archive, unexpected preexisting app, failed trust
   assessment, or launch failure blocks acceptance.

PR and merge-queue CI runs only **offline regression tests** for these
guards; they do not install an unsigned app and do not simulate a successful
Apple notarization. The existing unsigned bundle smoke test only covers a
*staged, uninstalled* executable and is not clean-install evidence.

## Actual clean-Mac acceptance remains a separate release prerequisite

A GitHub-hosted runner is freshly allocated for a job but is **not** a
separately provisioned retail Mac or a guarantee of a blank macOS image.
Before claiming that `opener-1148` has been fully exercised for a public
release, a maintainer must install the **same approved notarized artifact**
on a newly provisioned supported Mac with no prior PDF Magic installation:

- Confirm the source artifact's commit, successful notarization run and
  checksum; verify Developer ID, stapling and Gatekeeper acceptance with
  `codesign --verify --deep --strict`,
  `xcrun stapler validate` and `spctl --assess --type execute`.
- Install into `/Applications` without replacing an existing app; open the
  application through Finder/Launch Services, confirm its first-run UI and
  absence of unexpected permission or quarantine bypass prompts.
- Verify the separately installed scanner is **not** silently installed or
  treated as available, and that opening PDFs cannot bypass the established
  scan gate. Only test a managed PDF flow after explicitly provisioning the
  scanner and valid signatures through the separately documented installation
  process. Record macOS version/architecture, artifact hash, steps, results,
  and any failures without storing user PDFs, secrets or private preferences.
- Do not mark distribution ready until this physical-machine acceptance has
  actually passed. The hosted runner's green check is insufficient on its own.

**Known upstream gap:** The existing Developer ID signing workflow publishes
`pdf-magic-opener-developer-id-signed` containing
`pdf-magic-opener-developer-id-signed.zip`, while the notarization workflow
requires `signed-macos-app` containing `PDFMagicOpener-signed.zip`.
The artifact handoff needs to be completed in the signing/notarization tasks;
this focused installation test does **not** relabel or bypass either artifact.
Until a successful, verified notarization run exists, the live clean-install
workflow must fail closed rather than claim an installation succeeded.
