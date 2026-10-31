# Preserve a working opener on failed migration (opener-0946)

The standalone `install-allow-and-open.sh` installer retains the previously
installed PDF scan-handler app until **all** migration and post-install steps
succeed. A failed bundle build or migration restores the existing app and its
original legacy filename when applicable, then re-registers the restored app.
The old app is never deleted during partial deployment.

Before updating executable helper files, the installer snapshots an explicit
allowlist of the files it overwrites into a private temporary directory. On
failure, those original program files are restored; newly created program
files are removed. Custom browser selections, `freshclam.conf`, signature
databases, Finder's saved backup, and user documents are never snapshotted
or rewritten by this recovery mechanism.

Unsafe symlinks, nonregular executable files, and conflicting paths stop
recovery rather than following links or overwriting unrecognized data. If a
filesystem problem prevents complete recovery, the private backup is retained
for manual repair instead of being discarded. Success removes the temporary
backup only after installation finishes. This does not change the scanner's
fail-closed policy or enable opening a PDF without a clean, fresh scan.

CI tests synthetic interrupted installation scenarios on disposable paths;
no real user installation, secrets, or PDF files are accessed.
