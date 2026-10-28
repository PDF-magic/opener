import Darwin
import Foundation

/// Writes a complete, already-encoded configuration to an existing directory.
/// Schema validation and the storage location belong to the configuration
/// model; this writer never changes existing scanner or UserDefaults settings.
enum AtomicConfigurationWriter {
  enum SaveError: Error {
    case invalidName
    case unsafeDirectory
    case unsafeDestination
    case unsafeLock
    case io(Int32)
  }

  static func save(_ contents: Data, in directory: URL, named name: String) throws {
    guard !name.isEmpty, name != ".", name != "..",
          !name.contains("/"), !name.contains("\u{0}") else {
      throw SaveError.invalidName
    }
    guard directory.isFileURL else { throw SaveError.unsafeDirectory }

    let parent = open(directory.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
    guard parent >= 0 else { throw SaveError.unsafeDirectory }
    defer { close(parent) }

    // A persistent, per-destination advisory lock serializes independent
    // processes through validation, staging, rename and directory sync.
    // Never unlink this file: deleting it could split writers across inodes.
    let lockName = ".\(name).lock"
    let lockFD = openat(parent, lockName, O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0o600)
    guard lockFD >= 0 else { throw SaveError.unsafeLock }
    defer { close(lockFD) }

    var lockInfo = stat()
    guard fstat(lockFD, &lockInfo) == 0,
          (lockInfo.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG),
          lockInfo.st_nlink == 1,
          lockInfo.st_uid == geteuid() else {
      throw SaveError.unsafeLock
    }
    // Protect a preexisting lock file too, without following hard links.
    guard fchmod(lockFD, mode_t(0o600)) == 0 else { throw SaveError.io(errno) }
    while flock(lockFD, LOCK_EX) != 0 {
      if errno == EINTR { continue }
      throw SaveError.io(errno)
    }
    defer { _ = flock(lockFD, LOCK_UN) }

    // A replaced/unlinked lock inode cannot safely coordinate new writers.
    var currentLock = stat()
    guard fstatat(parent, lockName, &currentLock, AT_SYMLINK_NOFOLLOW) == 0,
          (currentLock.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG),
          currentLock.st_dev == lockInfo.st_dev,
          currentLock.st_ino == lockInfo.st_ino else {
      throw SaveError.unsafeLock
    }

    var current = stat()
    if fstatat(parent, name, &current, AT_SYMLINK_NOFOLLOW) == 0 {
      guard (current.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG) else {
        throw SaveError.unsafeDestination
      }
    } else if errno != ENOENT {
      throw SaveError.io(errno)
    }

    // Exclusive creation in the same directory guarantees rename is atomic
    // on the same filesystem. Never expose partially serialized bytes.
    let temporary = ".\(name).\(UUID().uuidString).tmp"
    let fd = openat(parent, temporary, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600)
    guard fd >= 0 else { throw SaveError.io(errno) }
    defer { unlinkat(parent, temporary, 0) }
    defer { close(fd) }

    // Enforce owner-only configuration access independent of process umask.
    // Fail closed before publishing if permission enforcement cannot succeed.
    guard fchmod(fd, mode_t(0o600)) == 0 else { throw SaveError.io(errno) }
    var temporaryInfo = stat()
    guard fstat(fd, &temporaryInfo) == 0 else { throw SaveError.io(errno) }
    guard (temporaryInfo.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG),
          (temporaryInfo.st_mode & mode_t(0o7777)) == mode_t(0o600) else {
      throw SaveError.unsafeDestination
    }

    try contents.withUnsafeBytes { buffer in
      guard let start = buffer.baseAddress else { return }
      var offset = 0
      while offset < buffer.count {
        let written = Darwin.write(fd, start.advanced(by: offset), buffer.count - offset)
        if written < 0 && errno == EINTR { continue }
        guard written > 0 else { throw SaveError.io(written < 0 ? errno : EIO) }
        offset += written
      }
    }
    guard fsync(fd) == 0 else { throw SaveError.io(errno) }

    // Reject a destination changed into a symlink/non-regular file while
    // writing. Schema and ownership checks are the caller's responsibility.
    if fstatat(parent, name, &current, AT_SYMLINK_NOFOLLOW) == 0 {
      guard (current.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG) else {
        throw SaveError.unsafeDestination
      }
    } else if errno != ENOENT {
      throw SaveError.io(errno)
    }
    guard renameat(parent, temporary, parent, name) == 0 else {
      throw SaveError.io(errno)
    }
    // Publish directory metadata as well as file contents.
    guard fsync(parent) == 0 else { throw SaveError.io(errno) }
  }
}
