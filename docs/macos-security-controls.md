# PDF Magic Opener and macOS security controls (opener-0826)

PDF Magic Opener adds a **local ClamAV scan before its own managed open**. It
does **not** replace, disable, approve, or certify any macOS security control.
A clean scan (including a verified clean-cache hit) permits only the opener's
next handoff; it does not mean that macOS will permit the destination to run,
that the file is harmless, or that opening outside PDF Magic Opener is blocked.

## Where the checks apply

| Control | PDF Magic Opener interaction and boundary |
| --- | --- |
| **File Quarantine** (`com.apple.quarantine`) | The scanner retains the existing extended attribute **byte-for-byte** on clean, cached, blocked, failed, and unscannable paths. Its historical `remove_quarantine(path)` hook is a no-op. The opener neither clears nor manufactures a user's quarantine approval. Files without an attribute are not claimed to be quarantined. |
| **Gatekeeper, Developer ID signing, and notarization** | These are **Apple's independent checks for executable software**, notably downloaded `.app` bundles. The opener scans app bundles recursively and rejects escaping symlinks, but a ClamAV verdict does not sign, notarize, approve, or override a bundle. Gatekeeper can still warn or block at launch. Do **not** assume that a PDF opening produces the same Gatekeeper prompt as launching a downloaded app. |
| **XProtect** | Apple's built-in malware protections remain independent and can block known malware even after an opener scan. A ClamAV clean result is not an XProtect verdict or a safety guarantee. |
| **Launch Services / default handlers** | Finder, the installed PDF document handler, and the optional Finder action feed the existing scan gate. After the gate passes, the launcher checks the **user-selected PDF-capable application** before handing the PDF to macOS; non-PDF files and `.app` bundles follow their normal system destinations. The Preferences app is not the PDF scan handler. An independent Finder/browser/system open that does not reach this handler is **not** controlled by this scan gate. |
| **Privacy permissions (TCC)** | macOS owns consent for protected files, folders, Automation, and other sensitive resources. The opener does not grant itself access, reset TCC, request an exemption, or circumvent an OS denial; an unavailable input or launch must fail. The optional live Finder test requires the operator's normal Automation consent. |
| **System Integrity Protection (SIP), sandboxing, and OS policy** | The opener does not change SIP, sandbox entitlements, system security settings, or managed-device restrictions. These protections are enforced by macOS, not by ClamAV. |

## Actual managed-opening sequence

1. A user deliberately opens a local PDF through the installed PDF handler or
   the Finder action (which also handles selected non-PDF types). Browser
   download observation or optional interception is **not** a universal macOS
   open interlock.
2. The scan gate validates the request, required ClamAV version and signature
   freshness (**last successful check within 48 hours**), fixed scanner
   arguments, local-file availability, and file identity. It checks actual
   bytes and bundle contents, not just a filename or download label.
3. A **complete clean** scan under the correct policy, or a currently valid
   90-day hash-based clean-cache record with the same mandatory checks, may
   proceed. Threats, errors, incomplete/skipped scans, timeouts, unreadable
   inputs, changed files, and unscannable bundles **do not open**. File identity
   and integrity are checked again before launch.
4. For PDFs, the opener verifies its selected PDF-capable destination (or a
   separately configured and verified PDF-only fallback). It leaves the
   quarantine attribute untouched and invokes the native launch helper.
   **macOS may still prevent opening**, independently of the scan result.

The source of truth is [the scan gate](../scan-and-open.py), its
[launcher](../file_launcher.py), and the
[Finder wrapper](../allow-and-open.sh). See also the
[quarantine-removal audit](macos-quarantine-removal-inventory.md),
[quarantined-PDF test](open-quarantined-pdf.md), and
[unscannable-file regression](unscannable-quarantine.md).

## Installation signing is not Gatekeeper approval

The [installer](../install-allow-and-open.sh) currently signs the locally
built PDF document-handler app using **ad hoc signing**
(`codesign --force --sign -`). Ad hoc signing is **not** a Developer ID
signature and does **not** notarize the app. Do not describe this installation
as Apple-notarized or guaranteed to pass Gatekeeper on another Mac. A
distributed build requires its own appropriate Developer ID signing,
notarization, and verification procedure; that distribution work is not part
of this documentation task. An installed handler's signature and a scanned
document's quarantine state are different things.

## Safe verification and troubleshooting

- On your **own harmless test file**, `/usr/bin/xattr -p com.apple.quarantine "/path/to/test.pdf"`
  reads the quarantine value without changing it. If the attribute is absent,
  the command reports that; do not add or strip attributes on user files to
  manufacture a success condition. A browser may or may not tag a particular
  download, so test results distinguish original tagging from synthetic
  markers on disposable fixtures.
- Check the [Finder double-click procedure](finder-double-click-test.md)
  before testing Finder's actual UI. The opt-in
  [Finder Open harness](../tests/general/finder-open.py) has a live mode,
  but ordinary CI does not automate an approval click or change defaults.
- If the scan reports missing/stale signatures, an unavailable scanner,
  an unscannable input, a changed file, or an unavailable selected app,
  **resolve that specific problem**. Do not remove quarantine, disable
  Gatekeeper with `spctl`, change macOS security policy, or force an
  alternative app launch to make a failing test pass.
- Existing [quarantine-retention tests](../tests/general/retain-os-quarantine.py)
  run on Ubuntu and macOS; the latter exercises real macOS xattrs.
  Additional [opening tests](open-quarantined-pdf.md) mock ClamAV and the final
  GUI launch. They **do not** prove a live Gatekeeper dialog, end-to-end
  notarization checks, or that unrelated apps cannot open a downloaded PDF.

## Apple documentation

- [Safely open apps on your Mac](https://support.apple.com/en-us/102445)
  explains Gatekeeper, signing, notarization, and approval prompts.
- [Protecting against malware in macOS](https://support.apple.com/guide/security-pdf/protecting-against-malware-sec469d47bd8/web)
  describes Apple's independent Gatekeeper and XProtect defenses.
- [App security overview](https://support.apple.com/guide/security/app-security-overview-sec35dd877d0/web)
  discusses File Quarantine, TCC, sandboxing, and SIP.
