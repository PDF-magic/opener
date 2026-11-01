# Developer ID signing for staged macOS distribution (opener-1140)

This is an **opt-in staged distribution build** of the SwiftUI
PDFMagicOpener.app and its reviewed native helper executables. It does not
replace or re-sign the separately installed, scan-gated PDF Magic Opener.app,
change the selected default PDF handler, or modify ClamAV signatures, browser
permissions, PDF files, quarantine, or user preferences. The per-user
installer keeps its existing ad hoc signature.

## Prerequisites

A valid Apple Developer Program **Developer ID Application** certificate with
its private key is required. Repository administrators must configure a
protected GitHub Actions environment named developer-id-release. Limit
deployment to the main branch and require trusted release approval. Provision
the following **encrypted environment secrets**, never repository files:

- APPLE_DEVELOPER_ID_CERTIFICATE_BASE64: a base64-encoded, password-protected
  PKCS#12 export of the Developer ID Application identity and private key.
- APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD: its export password.

Never commit, print, inspect, upload, or share the private key or certificate
export. The manual workflow imports it into a temporary locked-down keychain
on a fresh macOS runner; the temporary certificate file and keychain are
deleted afterward. No pull-request workflow receives signing secrets.

## Signing and validation

After reviewing the intended main revision and required CI, manually dispatch
**Sign staged macOS Developer ID distribution**, entering the ten-character
Apple team ID and the complete Developer ID Application signing identity name
(or its 40-character SHA-1 hash).

1. Xcode builds the Release scheme with signing disabled in temporary derived
   data. The helper packager stages and validates a separate application copy.
2. The signer checks the complete reviewed helper inventory and rejects unsafe
   symlinks, unexpected executable files, unreviewed nested code, and invalid
   Safari extension metadata.
3. It signs each native helper, any reviewed embedded LoginItems helper apps,
   the sandbox-entitled Safari app extension, then the outer application using
   a hardened runtime and trusted timestamp. There is no ad hoc fallback.
4. It independently checks **every component** using strict codesign
   verification, asserting the expected Apple team, Developer ID Application
   authority, and hardened-runtime flag. A failed signature blocks packaging.
5. The signed ZIP is extracted into another temporary directory and every
   signature is validated again before an inspection-only artifact is uploaded.

To revalidate a previously signed and extracted staged app on macOS without
any private key:

```sh
python3 scripts/sign_developer_id.py --app /path/to/PDFMagicOpener.app \
  --team-id TEAMID1234 --verify-only
```

## Remaining public distribution gates

**Signing alone does not establish release readiness.** The signed artifact
must still undergo Apple notarization and applicable stapling, Gatekeeper
assessment on a clean supported macOS system, and final real-world scanner,
browser, quarantine and preference-preservation tests. The Safari extension
remains inactive. No store submission, notarization, automatic installation,
or public release is performed by this signing workflow. The existing
source-only GitHub Release workflow and browser distribution audit remain
unchanged.

Run the credential-free CI regression with
`PYTHONPATH=. python3 tests/general/developer-id-signing.py -v`.
Actual signing verification runs on macOS only after a protected, manually
dispatched release environment has valid credentials.
