# Selected-path symbolic-link change detection (opener-0829)

The Built-in gate resolves local paths for its scanner and launcher, but also
retains a transient snapshot of every symbolic link in the **original selected
path**, including intermediate links. Retargeting, replacing, removing or
introducing a link fails closed with the established path-free file-changed
message. The checks cover queue waits, initial hashing, clean-cache reuse,
completed ClamAV scans, and launch handoff. Identical target bytes cannot
authorize a changed link.

Legitimate unchanged links remain supported. All full-byte hashing, file
identity checks, ClamAV decisions, clean-cache policy, quarantine preservation
and selected application settings remain unchanged.

Run `PYTHONPATH=. python3 tests/scanner/symbolic-link-changes.py -v` on Linux
or macOS. Both platforms register the suite in CI.
