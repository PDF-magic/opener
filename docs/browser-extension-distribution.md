# Browser extension distribution and signing audit (opener-0613)

**Status: NOT RELEASE READY.** This is a verification checklist, not a publication
or signing workflow. The WebExtension currently shows **Not active** and cannot
scan, sanitize, or open PDFs; neither a successful build nor a store signature
would authorize PDF handling. No publisher accounts, signing identities,
certificate files, profiles, or signing credentials are used or inspected by CI.

## Intended distribution channels

| Channel | What this repository actually packages | Signing and release requirement | Current blocker |
| --- | --- | --- | --- |
| **Chrome Web Store** (Chrome; also used by **Brave**, **Arc**, and **Vivaldi** where Chrome Web Store extensions are supported) | `npm run package:chrome` creates a validated, **not a signed CRX**, ZIP with its MV3 manifest at the root. | Upload the ZIP using a verified Chrome Web Store developer account; Google handles store distribution/signing. Review listing, permissions, and actual installed-extension behavior. | Not submitted, reviewed, published, or signed by the store; extension remains inactive. |
| **Microsoft Edge Add-ons** | The same Chromium upload ZIP; Edge has no separate release package or identity here. | Use a registered Edge Partner Center developer account; submit the ZIP for Microsoft review and store conversion to CRX. Verify Edge installation and update behavior independently. | No Edge Add-ons submission or signed CRX; existing Edge smoke checks do not test store installation. |
| **Opera Add-ons** | The shared Chromium ZIP is a candidate, not an Opera-approved package. | Confirm Opera's manifest and listing rules, submit with the Opera Add-ons publisher account, and complete Opera moderation and final browser installation checks. | No Opera submission or approval; Opera compatibility tests are not store review. |
| **Firefox AMO (listed)** | `npm run package:firefox` creates a Firefox-specific **not a signed XPI** ZIP (MV3 `background.scripts`). | Replace/register the `example.invalid` Gecko development ID with a unique publisher-owned ID; submit to AMO for validation, review, and **Mozilla signing**. | Placeholder Gecko ID, no AMO publisher submission, and no signed XPI. |
| **Firefox AMO (unlisted)** / self-distribution | The same unsigned Firefox ZIP. | A production Gecko ID and **Mozilla signing** through AMO are still mandatory for ordinary Firefox release installation, even without a public AMO listing. | Same missing identity and signature; an unsigned ZIP is not a release XPI. |
| **Safari Mac App Store** | Xcode builds the macOS host app with embedded `PDFMagicOpenerSafari.appex` (not a standalone browser ZIP). CI deliberately uses `CODE_SIGNING_ALLOWED=NO`. | Sign **both** host app and extension with an authorized Apple Developer Program distribution identity/provisioning configuration; archive and submit through App Store Connect for review. | No verified distribution team, signing or provisioning configuration, signed archive, or App Store approval. |
| **Safari Developer ID** (outside Mac App Store) | Same embedded macOS app-extension bundle, unsigned in CI. | Sign the app and embedded extension with an authorized Developer ID identity, enable applicable hardened-runtime/distribution settings, complete Apple **notarization**, and verify the distributed app after stapling. | No Developer ID signing or notarization pipeline or validated release artifact. |
| **Unpacked development** (**Chromium**, Chrome, Brave, Arc, Vivaldi, Opera, Edge; Firefox temporary debugging) | Built local directories or extracted ZIPs for compatibility and smoke testing. | No store signature needed for supported developer-mode testing. Use browser-specific development restrictions; do not present unpacked artifacts as public installable releases. | Smoke tests establish only local behavior, not store eligibility or production signatures. |

The Chromium-family row describes a **shared delivery route**, not a claim that
Brave, Arc, Vivaldi, Opera, or Edge automatically accepts or activates this
extension. In particular, Vivaldi documents Chrome Web Store support; each
browser's separately maintained compatibility test remains necessary. Opera
and Edge have their own publisher channels as listed above. No separate
Brave/Arc/Vivaldi signing credentials are presently needed for the shared
Chrome Web Store route.

## What CI verifies—and deliberately cannot verify

Run from the repository root after installing Node.js 20+:

```sh
cd extensions/webextension
npm run package:chrome
npm run package:firefox
npm test
cd ../..
python3 test-extension-distribution.py -v
python3 test-safari-extension-target.py -v
```

The audit checks the **actual** generated ZIP entries and byte-for-byte built
assets, both target manifests, the Firefox development-only ID, the embedded
Safari target, its minimal sandbox entitlement, and the continued unsigned
macOS CI build. Its checks are wired into required PR CI before artifacts are
uploaded. Existing browser runtime tests and macOS embedded-bundle checks
remain separate. Neither tests nor unsigned artifacts prove publisher identity,
store acceptance, Apple code signatures, notarization, or end-user installation.
Those require approved accounts, human review, and production-channel checks
**outside** this source-only task. Do not add credentials to the repository or
attempt automated signing on untrusted PR workflows.

Before any public release, resolve the corresponding blockers above, review
current store policy and account requirements, validate the exact signed or
store-delivered binary on supported browsers/macOS, and independently verify
all native scanner gates, quarantine, and saved user preferences. Updating this
audit is not permission to activate the extension.

## Primary publisher guidance

- [Chrome Web Store ZIP and listing preparation](https://developer.chrome.com/docs/webstore/prepare)
- [Microsoft Edge Add-ons packaging and hosting](https://learn.microsoft.com/en-us/microsoft-edge/extensions/publish/hosting-and-updating)
- [Opera Add-ons publishing guidelines](https://help.opera.com/en/extensions/publishing-guidelines/)
- [Firefox signing and listed/unlisted distribution](https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/)
- [Firefox add-on ID requirements](https://extensionworkshop.com/documentation/develop/extensions-and-the-add-on-id/)
- [Safari app, extension signing and notarized distribution](https://developer.apple.com/documentation/safariservices/distributing-your-safari-web-extension)
- [Vivaldi's Chrome Web Store compatibility](https://help.vivaldi.com/desktop/appearance-customization/extensions/)
