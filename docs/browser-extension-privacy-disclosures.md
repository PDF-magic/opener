# Browser extension privacy disclosures (opener-1152)

**DRAFT — NOT PUBLISHED OR RELEASE READY.** The statements below describe the
current **inactive browser extensions**, not a shipped service or the separate
installed macOS scanner. Reverify the exact submitted build, store forms and
public policy URL before publishing. Nothing here enables scanning or changes
browser permissions.

## Public-facing extension privacy policy (current implementation)

### Purpose and current functionality

PDF Magic Opener's browser extension is an **inactive integration scaffold**.
Its toolbar explains that it cannot scan, sanitize or open PDFs. A user may
choose the local `pdfmagicopener://preferences` link to request that macOS open
the separately installed app's preferences. The browser integration does not
currently monitor downloads or websites, connect to the scanner, or provide a
malware-clean verdict.

### Data collected, used, retained or shared

**No user data is collected or transmitted by the current browser extension.**
The extension does not read or retain PDF files or their contents, local file
paths, filenames, download source URLs, browsing histories, website content,
cookies, credentials, account details or location. It has no active analytics,
advertising, telemetry, cloud-upload, or external data-transfer functionality.

The extension sends **no personal data to the publisher, advertisers, analytics
providers, or other third parties**, and does not sell user data. It stores no
browser-extension user records or scan histories, so there are no
extension-collected records to access, export or delete. The browser and the
separately installed macOS application may handle their own information under
their respective controls; this statement does **not** claim that the native
scanner never reads files or that browsers never maintain download histories.

### Browser access and choice

- **Chrome / Chromium / Edge / Opera and compatible Chromium browsers:** no
  required browser API permissions and no host or website permissions. The
  manifest lists **optional `downloads`**, but listing it does not grant it,
  and the inactive extension does not request it or monitor downloads.
- **Firefox:** the same required/optional permission boundary, with
  `browser_specific_settings.gecko.data_collection_permissions.required:
  ["none"]` declaring no extension data collection or transmission.
- **Safari:** the embedded extension additionally declares required
  `nativeMessaging` for a local extension handler. The current handler only
  answers bounded `native.status` requests with inactive status; it does not
  send PDF bytes, document paths or scan requests to the macOS app. There are
  no website-origin grants. Safari extension enabling remains the user's choice.

A future *activated* download-monitoring feature could expose filenames,
download URLs and download history when the user explicitly enables it and
approves a browser permission prompt. **It is not active now.** Before any such
feature is released, update the policy, store data-use disclosures and user
notice/consent, and review the native scanner boundary. Denial or revocation of
any browser permission must not bypass scanning, signature freshness, document
integrity checks, quarantine or user-selected PDF opening preferences.

### User controls and questions

Users may disable or uninstall the extension through their browser's extension
settings. They do not need to grant optional download monitoring for the
separate native PDF handler. For non-sensitive questions about the project,
use the public repository issue tracker at
https://github.com/PDF-magic/opener/issues. **Do not post private document
details or personal data in public issues**; consult
https://github.com/PDF-magic/opener/blob/main/SECURITY.md for the project's
confidential security-reporting procedure. A publisher-controlled privacy
contact and a stable, publicly accessible policy URL must be confirmed before
any actual store submission.

## Store submission privacy fields (draft copy, not certifications)

| Channel | Single purpose / permission explanation | Current data-use disclosure |
| --- | --- | --- |
| **Chrome Web Store** (also Brave, Arc, Vivaldi where supported) | Inactive PDF Magic Opener browser-integration UI; no page access; optional `downloads` is not used or requested. No remotely hosted code. | No user data collected, transmitted, sold, or shared. Enter these answers in the Privacy practices form only after reviewing the submitted ZIP. |
| **Microsoft Edge Add-ons** | Same inactive UI; no host access; optional `downloads` is inactive. No remote code. | No user data collected or shared; enter the same scope in the Partner Center Privacy page and verify the live policy URL. |
| **Opera Add-ons** | Shared inactive Chromium ZIP, optional `downloads` unused; no website permissions. | No data collection or sharing in this build; verify Opera's current listing questionnaire before submission. |
| **Firefox AMO** | Inactive Firefox build; no required browser or site grants; optional `downloads` unused. | Gecko manifest explicitly declares `required: ["none"]`; check the actual AMO submission against this exact manifest. |
| **Safari** | Inactive Safari extension embedded in macOS app, with local `nativeMessaging` status handler only and no host origins. | No browser-extension user data collection or external transmission; the installed native app is a separate processing boundary. Confirm App Store / Developer ID listing requirements independently. |

## Mandatory prepublication review

1. Rebuild and inspect **each actual channel artifact** against source manifests,
   active background, popup, Safari handler and the Firefox Gecko declaration.
   No unsigned CI ZIP, inactive popup, or test makes the extension release-ready.
2. Host and verify an accessible, publisher-controlled **privacy policy URL**;
   confirm a responsible publisher identity and **privacy contact**. This draft's
   repository path is not an assertion that the URL was submitted or approved.
3. Complete Chrome Web Store **Privacy practices**, Edge Partner Center
   **Privacy**, Mozilla/AMO data-use declarations, and the applicable Opera and
   Safari submission fields with truthful, channel-specific answers.
4. Re-review disclosures **before enabling downloads monitoring, native PDF
   handoff, network requests, analytics or any new permission**. Obtain
   required user notice and affirmative consent before collecting data; never
   reuse this no-data statement after behavior changes.
5. Independently clear release signing, package verification, real-browser
   activation and scanner safety gates in the distribution checklist.

Source contracts:
[extension permissions](../extensions/webextension/permissions.md),
[permission explanations](../extensions/webextension/permission-explanations.md),
[distribution readiness](browser-extension-distribution.md).

Publisher references:
[Chrome Web Store user-data policy](https://developer.chrome.com/docs/webstore/program-policies/user-data-faq),
[Edge Add-ons privacy submission](https://learn.microsoft.com/en-us/microsoft-edge/extensions/publish/publish-extension),
[Firefox built-in data consent](https://extensionworkshop.com/documentation/develop/firefox-builtin-data-consent/).
