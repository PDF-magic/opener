# Extension store description drafts (opener-1151)

**Draft copy only — NOT RELEASE READY, not submitted, not approved, and not published.**
These are copy-ready proposed descriptions for future publisher review, not live listings.
The browser extensions are inactive; installation does not make browser PDFs safe or
connect a browser to the native scan gate. The separate PDF Magic Opener macOS
application scans locally available files with ClamAV before a verified opening.

Each short description is limited to 132 characters. Recheck the destination
store's current field limits, policies, publisher identity, permissions,
screenshots, and locale before any submission. Store privacy questionnaires
and data-use disclosures are tracked separately (opener-1152); these descriptions
are not a substitute for those disclosures. Distribution credentials, account
approval, signing, and actual store submission are out of scope. See
[browser extension distribution](browser-extension-distribution.md) for blockers.

## Chrome Web Store

### Short description

~~~text
Inactive PDF Magic Opener companion for macOS. Browser PDF scanning and interception are not enabled.
~~~

### Full description

~~~text
PDF Magic Opener for Chrome is an inactive browser companion to the separate macOS PDF-opening application.

Status: Not active. This extension cannot scan, sanitize, or open PDF files. It does not intercept browser PDF viewers, monitor downloads, or authorize PDF opening.

The separately installed PDF Magic Opener macOS application uses ClamAV to scan locally available PDFs and checks the result before a verified handoff to your selected PDF-capable application. Installing this extension does not connect Chrome to that scanner.

The toolbar reports its inactive state and provides a user-initiated shortcut to native PDF Magic Preferences when the macOS application is installed. No required browser or website permissions are requested. The optional downloads permission is declared, but monitoring is not active.
~~~

## Microsoft Edge Add-ons

### Short description

~~~text
Inactive PDF Magic Opener companion for Edge on macOS; automatic browser PDF scanning is unavailable.
~~~

### Full description

~~~text
PDF Magic Opener for Microsoft Edge is an inactive browser companion to a separate macOS PDF-opening application.

Status: Not active. This extension cannot scan, sanitize, or open PDF files. It does not intercept Edge PDF viewers, monitor downloads, or authorize PDF opening.

The separately installed PDF Magic Opener macOS application scans locally available PDFs with ClamAV before a verified handoff to your chosen PDF-capable application. This extension does not connect Edge to that scanner.

The toolbar shows the inactive status and offers a user-initiated link to native PDF Magic Preferences when installed. The shared Chromium package requests no required website or browser permissions. The optional downloads permission is declared but monitoring is not active.
~~~

## Opera Add-ons

### Short description

~~~text
Inactive PDF Magic Opener companion for Opera on macOS. Browser PDF protection is not active.
~~~

### Full description

~~~text
PDF Magic Opener for Opera is an inactive browser companion to a separate macOS PDF-opening application.

Status: Not active. This extension cannot scan, sanitize, or open PDF files. It does not intercept Opera PDF viewers, monitor downloads, or authorize PDF opening.

The separately installed PDF Magic Opener macOS application scans locally available PDFs with ClamAV before verified opening in your selected PDF-capable application. This extension does not connect Opera to that scanner.

The toolbar displays the inactive state and offers a user-initiated shortcut to native PDF Magic Preferences if installed. The shared Chromium package requests no required website or browser permissions. The optional downloads permission is declared but monitoring is not active.
~~~

## Firefox AMO

### Short description

~~~text
Inactive PDF Magic Opener companion for Firefox on macOS. PDF scanning requires the separate native app.
~~~

### Full description

~~~text
PDF Magic Opener for Firefox is an inactive browser companion to a separate macOS PDF-opening application.

Status: Not active. This extension cannot scan, sanitize, or open PDF files. It does not intercept Firefox PDF viewers, monitor downloads, or authorize PDF opening.

The separately installed PDF Magic Opener macOS application scans locally available PDFs with ClamAV before verified opening in your chosen PDF-capable application. This extension does not connect Firefox to the scanner.

The toolbar displays the inactive status and offers a user-initiated shortcut to native PDF Magic Preferences when the application is installed. No required website or general browser permissions are requested. The optional downloads permission is declared but monitoring is not active.
~~~

## Safari App Store

### Short description

~~~text
Inactive Safari companion for PDF Magic Opener on macOS; browser PDF scanning is not enabled.
~~~

### Full description

~~~text
The Safari extension included with the PDF Magic Opener macOS host application is an inactive browser companion.

Status: Not active. This extension cannot scan, sanitize, or open PDF files. It does not intercept Safari PDF viewers, monitor downloads, or authorize PDF opening.

The separate PDF Magic Opener macOS application scans locally available PDFs with ClamAV before verified opening in your selected PDF-capable application. The Safari extension has no verified scan-before-render connection to the app.

Its toolbar reports the inactive state and offers a user-initiated shortcut to PDF Magic Preferences if the native application is installed. Safari's extension manifest declares nativeMessaging but no website access; this is not an active scanner connection. The downloads permission is optional and monitoring is not active.
~~~

The Chrome copy is also the starting point for Chrome Web Store-compatible
Brave, Arc, and Vivaldi users; those are not separate confirmed store releases.
Edge and Opera require their own publisher review. Firefox requires a real Gecko
identifier and Mozilla signing. Safari distribution requires approved Apple
signing and the host application's distribution channel. Do not publish these
drafts before those independent release prerequisites and security reviews.
