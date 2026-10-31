import Foundation
import Darwin

// Destructive, explicitly requested operation on the optional metadata store.
// This never reads PDF files, alters scanner configuration, changes the
// unrelated 90-day clean-scan cache, or enables history collection.
enum ClearScanHistoryOutcome {
  case cleared
  case nothingToClear
  case unavailable
}

enum ClearScanHistoryStore {
  static func clear(
    databaseURL: URL = RecentScanHistoryReader.defaultDatabaseURL
  ) -> ClearScanHistoryOutcome {
    guard databaseURL.isFileURL,
          databaseURL.lastPathComponent == "scan-history.sqlite3",
          databaseURL.deletingLastPathComponent().lastPathComponent == "scan-history" else {
      return .unavailable
    }

    let parent = databaseURL.deletingLastPathComponent()
    var original = stat()
    guard lstat(parent.path, &original) == 0 else {
      return errno == ENOENT ? .nothingToClear : .unavailable
    }
    guard isPrivateDirectory(original) else { return .unavailable }

    // Resolve trusted ancestor aliases such as /var -> /private/var,
    // without resolving the private directory or any final file component.
    let resolvedParent = parent.resolvingSymlinksInPath()
    let directoryFD = Darwin.open(
      resolvedParent.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
    )
    guard directoryFD >= 0 else { return .unavailable }
    defer { _ = Darwin.close(directoryFD) }

    var directory = stat()
    guard fstat(directoryFD, &directory) == 0,
          isPrivateDirectory(directory),
          directory.st_dev == original.st_dev,
          directory.st_ino == original.st_ino else {
      return .unavailable
    }

    // Only these four optional SQLite artifacts may be removed. Never
    // recursively clear the folder or delete operational logs/cache files.
    let names = [
      "scan-history.sqlite3",
      "scan-history.sqlite3-wal",
      "scan-history.sqlite3-shm",
      "scan-history.sqlite3-journal"
    ]
    var verified: [(name: String, device: dev_t, inode: ino_t)] = []

    for name in names {
      var metadata = stat()
      let status = name.withCString { fstatat(directoryFD, $0, &metadata, AT_SYMLINK_NOFOLLOW) }
      if status != 0 {
        if errno == ENOENT { continue }
        return .unavailable
      }
      guard isPrivateRegularFile(metadata) else { return .unavailable }

      // O_NOFOLLOW makes a swapped symlink fail, including sidecar files.
      let descriptor = name.withCString {
        openat(directoryFD, $0, O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
      }
      guard descriptor >= 0 else { return .unavailable }
      var pinned = stat()
      let inspected = fstat(descriptor, &pinned) == 0
        && isPrivateRegularFile(pinned)
        && pinned.st_dev == metadata.st_dev && pinned.st_ino == metadata.st_ino
      _ = Darwin.close(descriptor)
      guard inspected else { return .unavailable }
      verified.append((name, pinned.st_dev, pinned.st_ino))
    }
    if verified.isEmpty { return .nothingToClear }

    // Check every entry before mutating anything. Recheck identity immediately
    // before unlinking each file; fail closed on substituted entries.
    for entry in verified {
      guard matches(entry, directoryFD: directoryFD) else { return .unavailable }
    }
    for entry in verified {
      guard matches(entry, directoryFD: directoryFD),
            entry.name.withCString({ unlinkat(directoryFD, $0, 0) }) == 0 else {
        return .unavailable
      }
    }
    guard fsync(directoryFD) == 0 else { return .unavailable }
    return .cleared
  }

  private static func isPrivateDirectory(_ info: stat) -> Bool {
    (info.st_mode & mode_t(S_IFMT)) == mode_t(S_IFDIR)
      && info.st_uid == getuid()
      && (info.st_mode & mode_t(0o077)) == 0
  }

  private static func isPrivateRegularFile(_ info: stat) -> Bool {
    (info.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG)
      && info.st_uid == getuid()
      && (info.st_mode & mode_t(0o077)) == 0
  }

  private static func matches(
    _ entry: (name: String, device: dev_t, inode: ino_t),
    directoryFD: Int32
  ) -> Bool {
    var current = stat()
    let status = entry.name.withCString {
      fstatat(directoryFD, $0, &current, AT_SYMLINK_NOFOLLOW)
    }
    return status == 0 && isPrivateRegularFile(current)
      && current.st_dev == entry.device && current.st_ino == entry.inode
  }
}
