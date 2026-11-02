# Gatekeeper-enabled first release launch (opener-1149)

This is a real Launch Services first-launch acceptance check for the macOS
preferences app, distinct from the existing Gatekeeper unsigned-code denial
test (gatekeeper-protections.md) and unsigned direct-executable smoke test.

## Prerequisites

A genuine result requires a Developer ID-signed, hardened-runtime, Apple-
notarized and stapled app from the exact current main commit. The protected
Developer ID signing and notarization workflows must first publish the
notarized-macos-app artifact containing PDFMagicOpener-notarized.zip.
Unsigned or ad-hoc-signed test builds are never accepted.

Known upstream dependency: the signing workflow currently publishes
pdf-magic-opener-developer-id-signed with an archive named
pdf-magic-opener-developer-id-signed.zip, but the notarization workflow expects
signed-macos-app with PDFMagicOpener-signed.zip. Align that handoff in the
separate release/signing task. Apple signing and notarization environments
must also be configured by an authorized maintainer. This task neither
changes them nor accesses credentials.

## Real macOS acceptance

Dispatch the GitHub Actions workflow Gatekeeper first launch of notarized
macOS app on main with the successful notarization_run_id and the expected
ten-character Developer ID team_id. The job:

1. Rejects absent/stale/unsuccessful notarization runs or the wrong workflow.
2. Extracts the real archive into ephemeral macOS runner storage, and requires
   the app not to exist in system or current-user Applications directories.
3. Independently checks the app identity, helper signatures, Developer ID team,
   hardened runtime and a valid stapled ticket.
4. Requires Gatekeeper to report assessments enabled, applies a real
   com.apple.quarantine marker only to the disposable extracted app, and
   requires an explicit Notarized Developer ID acceptance from spctl while
   quarantine remains present.
5. Launches the real app through /usr/bin/open and Launch Services, not by
   direct execution. It rejects prior processes, a denial, premature exits,
   missing processes and apps that do not remain running; stops only the new
   test app and rechecks Gatekeeper remains enabled.

A GitHub macOS hosted runner is ephemeral, but it cannot prove interactive
Finder dialogs or a freshly created OS user account. Before public release,
repeat with the distributed archive on a freshly provisioned supported Mac
and record the OS version, archive SHA256, signing identity, notarization
status and visible first-launch outcome. Do not use security overrides.

The test never disables Gatekeeper, clears quarantine, changes system trust,
installs or modifies the PDF scanner, registers PDF handlers, resets
preferences, opens private PDFs or accesses signing secrets. Gatekeeper can
legitimately update quarantine metadata after an actual launch, so metadata
is checked before the first launch and during assessment.

## Automated checks

Each PR, merge group and main push executes portable fail-closed contract
tests. From the repository root:

    python3 tests/general/gatekeeper-first-launch.py -v

A real notarized first launch is run only by the separate manual macOS
workflow when all prerequisites are present. Do not claim actual public
distribution acceptance from portable CI alone.
