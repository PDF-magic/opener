# macOS quarantine-removal call inventory (opener-0814)

## Finding

**No active quarantine-attribute removal call was found in the tracked
runtime source tree at the audited revision.** There is **one historically
named compatibility hook** and **one caller**, neither of which removes
quarantine. This is a source-code inventory, not a claim about unrelated
third-party applications, compiled external binaries, or untracked local files.

| Location | Call or operation | Effect | Classification |
| --- | --- | --- | --- |
| [`scan-and-open.py`, `remove_quarantine(path)`](../scan-and-open.py) | Definition near line 759 | Its only executable statement is `return None`; no subprocess, xattr change, or filesystem mutation | **Inert compatibility hook** |
| [`scan-and-open.py`, `scan_and_open`](../scan-and-open.py) | `remove_quarantine(path)` call near line 997 | Invokes inert hook after destination verification, before another integrity check and safe launch | **One call to inert hook; not a removal** |
| [`tests/general/retain-os-quarantine.py`](../tests/general/retain-os-quarantine.py) | Negative assertions against `os.removexattr`/`xattr`; macOS-only `os.setxattr`/`os.getxattr` | Tests that tagged PDFs retain their extended attribute after fresh, cached, and blocked scans | **Test assertions and fixture setup, not production deletion** |
| [`maximum_sanitized_copy.py`](../maximum_sanitized_copy.py) | `preserve_quarantine` policy | Declares that future sanitized output must preserve quarantine | **Preservation contract, not a removal** |

The [`allow-and-open.sh`](../allow-and-open.sh) entry point delegates to the
scanner. The [`install-allow-and-open.sh`](../install-allow-and-open.sh)
installer deploys the scanner and native components. Neither of these inspected
shell entry points strips `com.apple.quarantine`. Keep the legacy hook for
compatibility; do not delete it in an inventory-only change.

## Reproducible audit

Run from the repository root:

```sh
python3 tools/audit_quarantine_removal.py
PYTHONPATH=. python3 tests/general/quarantine-removal-inventory.py -v
PYTHONPATH=. python3 tests/general/retain-os-quarantine.py -v
```

The read-only auditor enumerates Git-tracked **runtime source** via
`git ls-files`, covering Python, Swift, shell, AppleScript, JavaScript,
Objective-C/C, Xcode project metadata, plist and workflow YAML. It excludes
documentation, test fixtures, its own pattern definitions, and secret-bearing
filenames; it never reads credentials, untracked files or user documents.

It reports source-file and line candidates for destructive `xattr -d`,
`xattr -c` (including combined flags), `removexattr`/`fremovexattr`/
`lremovexattr`, related removal wrappers, and quarantine-specific
Foundation/LaunchServices resource writes. Any candidate fails the audit until
reviewed. A Python AST check additionally requires exactly one definition and
call of `remove_quarantine` in the real scanner, and verifies its only
executable statement remains `return None`.

The new regression tests include examples of dangerous operations in Python,
Swift, shell and spawned command arguments, and prove a newly added Git-tracked
source file with `os.removexattr` triggers a finding. Read-only xattr lookups
are not treated as deletions. CI runs the auditor and regressions alongside
existing quarantine-retention tests on Ubuntu and macOS; the latter also tests
actual xattr persistence on macOS.

### Limits

Static analysis cannot prove the behavior of compiled binaries, external
dependencies, dynamically constructed arbitrary commands or excluded test
fixtures. It locates recognizable removers in tracked runtime sources and
fails closed on new candidates; it does not claim that arbitrary external
processes are controlled. Any later metadata-changing code needs specific
security review. Existing scanner, integrity, quarantine, Gatekeeper and
user-preference behavior are unchanged.
