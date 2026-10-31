# Mounted network-volume scan policy — opener-0843

**Policy: permit an already-accessible, mounted network-volume document under
the same mandatory scan and verified-opening requirements as an ordinary local
document. Fail closed if the mounted filesystem becomes unavailable.** There
is no network-volume exception, scanner bypass, different application choice,
or automatic retrieval from a URL.

This applies to ordinary local filesystem paths on SMB/NFS and other mounted
network filesystems, as well as local disks. The existing request gate still
accepts only regular files and .app bundles (including valid aliases); it
rejects raw smb:, nfs:, HTTP(S) and other remote URL requests.

scan-and-open.py calls require_accessible_volume() using os.statvfs()
after strict path resolution and type validation at both public admission
gates. A failed mount metadata probe produces one path-free, fixed error
before acquiring a scanner queue slot, touching the clean cache, starting
ClamAV or opening anything. The same check runs before and after every
full-byte/file-identity verification, including on cached-clean paths,
following completed scans, and immediately before the native launch handoff.
If the share disappears between these checkpoints, the normal file reads,
identity comparisons and opening checks must also succeed; failures do not
authorize opening.

**A network mount is not intrinsically treated as clean or unsafe.** Existing
mandatory ClamAV flags, signature checks, integrity hashes, device/inode and
timestamp identity checks, fail-closed scan results, quarantine preservation,
cached-verdict validation, selected PDF handler and fallback preferences are
unchanged. Network operations may still be subject to normal filesystem
latency or unavailable-server failures; no new remote mounting, downloading,
copying, credential handling, or background access is introduced.

Portable CI uses an isolated synthetic mounted-share fixture and mocked
statvfs success/failure transitions to assert normal scanning, fail-closed
admission before side effects, and no handoff if the volume disappears during
a scan. The fixture is **not a live SMB/NFS mount**; production behavior still
depends on the operating system's mounted filesystem implementation.
