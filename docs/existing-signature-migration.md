# Existing signature-file migration (opener-0941)

The separately packaged SwiftUI preferences app does not install or relocate
the native scan gate. Its current live database remains
`~/Library/Application Support/Studio/allow-and-open/signatures`.
This migration helper does **not** change that scanner path, install a new
service, or run automatically before legacy-installation discovery.

For an installation workflow that has already **identified** a legacy
signature directory and selected the correct destination and installed
ClamAV executable, invoke:

```sh
python3 scripts/migrate_signature_files.py \
  --source "/verified/legacy/signatures" \
  --destination "/chosen/installed/signatures" \
  --scanner "/opt/homebrew/bin/clamscan"
```

The destination must not exist, even if empty. In that case, the helper
preserves it completely. The helper copies only recognized main/daily and
optional bytecode ClamAV CVD/CLD files, plus ordinary user-defined signature
formats. It rejects missing, ambiguous, truncated, nonregular, linked or
incompatible signature files, verifies the staged database with the supplied
ClamAV scanner, and publishes the verified snapshot as one directory rename.

The old source remains intact, including any user data, preferences and
unrecognized files. No logs, proxy credentials or other unrelated files are
read or imported. Crucially, **no last-successful-update timestamp is
copied or fabricated**. The existing 48-hour scanner gate remains closed
until the normal updater completes and records a new successful update.
Migration cannot substitute for FreshClam verification or give permission to
open a document.

Automatic source detection, selecting a different installed destination,
installation switching, and LaunchAgent/Quick Action migration are separate
existing-installation checklist tasks. Those steps must coordinate use of
this helper before changing the authoritative signature path.
