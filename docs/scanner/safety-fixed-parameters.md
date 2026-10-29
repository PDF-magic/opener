# Scanner parameters that must remain safety-fixed (opener-0398)

This is an inventory of the *currently enforced Built-in scan gate*, not a new settings interface. The installed `scan-and-open.py` and `scanner_argument_validation.py` are authoritative. The Advanced Scanning page is read-only. Neither saved preferences, document contents, nor caller-supplied request labels may override the following requirements.

## Fixed scanner invocation

| Boundary | Mandatory setting and rationale |
| --- | --- |
| Engine | `scanner_path()` uses the installed executable candidates and checks supported **ClamAV 1.4 or 1.5** versions; `--version` is the only separate version-probe option. A user-selected executable, unverified engine or arbitrary shell command cannot authorize opening. |
| Signatures | `--database=<installed signatures>` targets the installed database, not a selected document's database. The gate requires nonempty `main` and `daily` signatures and a successful update within **48 hours**, including cache hits; unavailable, invalid or future records block opening. |
| Scan coverage | `--recursive`, `--follow-file-symlinks=2` and `--follow-dir-symlinks=2` stay enabled. Separately reject external, dangling or cyclic links in an application bundle before traversing it. |
| Unscannable and suspicious content | `--alert-exceeds-max=yes` and `--alert-encrypted=yes` remain enabled. No detection, warning, skipped item, scan error or incomplete verdict can count as clean. |
| Standalone PDFs | `--max-filesize=0` and `--max-scansize=0` are the existing no-*configured*-limit mode, **not** permission to ignore ClamAV's own engine limits. |
| Other files and bundles | `--max-filesize=512M` (**512 MB** per file) and `--max-scansize=1024M` (**1 GB** aggregate) remain separate from the PDF mode. |
| Timeouts | `--max-scantime=0` is the current engine option; a separately enforced process timeout is mandatory. Its maximum is **30 minutes** for PDFs and **3 minutes** for other inputs. An in-memory `ScanSecurityPolicySnapshot` may only tighten those maxima, not extend or disable them. |
| Exact argv | `--no-summary` and the literal `--` separator must remain; the document path is one operand after the separator. Every argument is checked before scanner spawn or reuse of a cached clean verdict. |

## Other fixed safety boundaries

- The ceiling is **two** concurrent active scans. The content-based clean cache expires after **90 days** and uses separate policy/PDF keys. Every attempted opening still checks signatures, file identity/content integrity and destination validity, including cache hits.
- Reject zero-length or unavailable inputs, unsupported entry types, escaping bundle symlinks, nonclean scanner responses and unverified application targets. Denials never turn into launch permission.
- Preserve `com.apple.quarantine` even after a clean scan: macOS Gatekeeper and related protections remain independent.
- Existing selected PDF destinations, UI preferences and request metadata (`protection_level`, `source_url` and download identifiers) are **not ClamAV options**. Preserve those user customizations without allowing them to select flags, skip scans, weaken signatures, remove quarantine or override opening decisions.

## Boundary for future optional configuration

**No new scanner overrides are authorized by opener-0398.** A later settings feature must not allow an arbitrary scanner/database, missing recursion or alerts, looser limits, bypassed signature/integrity checks, relaxed cache admission, quarantine removal or opening after an incomplete scan. Such a policy change requires an independent security review and new fail-closed regression tests, not just an exposed setting.

Run `python3 test-scanner-fixed-safety-parameters.py -v` alongside `test-scanner-arguments.py` and `test-scan-policy-snapshot.py`. The checks audit both exact scanner modes and the named invariant boundaries without running ClamAV or changing installed preferences.
