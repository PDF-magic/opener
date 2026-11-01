# Handling quarantined files (opener-1126)

PDF Magic Opener respects **macOS File Quarantine**. A file downloaded from
the internet *may* carry the `com.apple.quarantine` extended attribute, which
macOS uses for its own security decisions. The opener does **not** create a
separate quarantine vault, move or delete the original, strip its quarantine
attribute, approve an app for Gatekeeper, or disable another macOS safeguard.
If the file had no quarantine attribute, the opener does not add one; absence
of that marker is **not** proof that a PDF was scanned or is safe.

## During a managed opening

1. Opening a locally available PDF through the installed PDF Magic Opener
   document handler or its Finder action enters the **Built-in** ClamAV scan
   gate. A download in a browser, an inline browser PDF, or another app's
   independent Open command is **not** automatically covered by this gate.
2. The gate checks file availability and identity, the supported scanner,
   its required definitions (last successful signature check within
   **48 hours**), scan completeness, and file integrity. A complete clean
   scan or a matching **90-day** verified clean-cache entry can proceed;
   a cache hit still requires the mandatory current checks.
3. The opener verifies the user-selected PDF application before handing it
   the *same* file, rechecking integrity immediately before launch. Any
   explicitly configured PDF-only fallback must independently pass
   verification. A clean result does **not** remove `com.apple.quarantine`
   or grant macOS permission to open or execute the file. macOS remains
   free to warn, deny, or apply its own controls.

The scanner's historical `remove_quarantine(path)` compatibility hook is
intentionally a **no-op**. Both a fresh clean scan and a verified clean-cache
handoff preserve an existing quarantine attribute **byte-for-byte**.
Gatekeeper mainly concerns executable applications; do not expect every
quarantined PDF to show an app-style Gatekeeper approval prompt.

## When opening is blocked

| Condition | What the opener does |
| --- | --- |
| **Malware detected or suspicious content** | Refuses the managed open; does not clear quarantine, create a clean-cache authorization, or silently open in another app. |
| **Incomplete or unscannable input** (limits, skipped content, encryption alerts, or ambiguous result) | Fails closed without a verified clean result, cached clean authorization, or application handoff. |
| **Scanner failure, unavailable/stale signatures, timeout, or cancellation** | Stops the request. No automatic bypass, quarantine removal, or success notification. |
| **Missing local file, unreadable path, changed bytes or symlink, or unavailable/unsafe destination** | Refuses the handoff; a clean verdict from an earlier file state cannot override the failure. |

A blocked file remains in its original location unless the **user or another
system component** moves it. PDF Magic Opener does **not** provide a
malware-quarantine repository or a restore/release-from-quarantine button.
Do not interpret a blocked opening as a promise that other applications
cannot access the file: the safeguard applies only to managed openings.

## Inspect and resolve safely

On **your own harmless test file**, you can inspect an existing quarantine
marker without modifying it:

```sh
/usr/bin/xattr -p com.apple.quarantine "/path/to/test.pdf"
```

An absent attribute simply means the marker is not present. To address a
**scanner or signature failure**, use the normal ClamAV installation/update
workflow and retry the managed open only after the prerequisite is healthy.
For an unavailable cloud or network file, make the trusted original locally
available through its normal provider, then retry through the installed
handler. For a suspicious or detected-malware result, **do not reopen the
file in another app to evade the block**; follow your security-response
procedure.

Never use `xattr -d`, `xattr -c`, Gatekeeper disabling commands, changed
scanner flags, or a different PDF handler as a workaround for a blocked
request. The opener does not modify your selected viewer, saved protection
preferences, installed scanner, or macOS security policy to resolve it.

## Implementation and verification

The [scan-and-open gate](../scan-and-open.py) and the
[macOS security controls guide](macos-security-controls.md) define the
actual protection boundary. See the
[unscannable-file regression](unscannable-quarantine.md),
[quarantined-PDF opening test](open-quarantined-pdf.md),
[quarantine-removal audit](macos-quarantine-removal-inventory.md),
[scanner failure policy](scanner/failure-response.md), and
[signature limitations](scanner/signature-limitations.md).

The [quarantine-retention regression](../tests/general/retain-os-quarantine.py)
covers clean, cached, and blocked paths; macOS CI also checks actual
extended-attribute bytes. The
[unscannable regression](../tests/general/unscannable-quarantine.py) checks
fail-closed paths. These automated tests do **not** certify a real Finder
approval dialog or an external viewer's GUI behavior.
