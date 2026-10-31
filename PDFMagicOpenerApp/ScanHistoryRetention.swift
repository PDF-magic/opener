import Foundation
import Darwin
import SQLite3

// Only the optional scan-history metadata store. History collection remains
// disabled until an independent opt-in integration explicitly enables it.
enum ScanHistoryExpiryOutcome {
  case removed(Int)
  case nothingToRemove
  case unavailable
}

enum ScanHistoryRetentionStore {
  static let allowedDays = [7, 30, 90, 365]
  static let defaultDays = 30

  static func settingsURL(databaseURL: URL = RecentScanHistoryReader.defaultDatabaseURL) -> URL {
    databaseURL.deletingLastPathComponent().appendingPathComponent("retention.json")
  }

  private static func privateDirectory(_ url: URL) -> Bool? {
    var info = stat()
    guard lstat(url.path, &info) == 0 else { return errno == ENOENT ? nil : false }
    return (info.st_mode & mode_t(S_IFMT)) == mode_t(S_IFDIR)
      && info.st_uid == getuid() && (info.st_mode & mode_t(0o077)) == 0
  }

  private static func privateFile(_ info: stat) -> Bool {
    (info.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG)
      && info.st_uid == getuid() && (info.st_mode & mode_t(0o077)) == 0
  }

  // Missing preferences mean 30 days, not consent to start collecting scans.
  // Malformed, substituted or nonprivate preferences are rejected.
  static func selectedDays(
    databaseURL: URL = RecentScanHistoryReader.defaultDatabaseURL
  ) -> Int? {
    guard databaseURL.isFileURL else { return nil }
    let parent = databaseURL.deletingLastPathComponent()
    guard let privateParent = privateDirectory(parent) else { return defaultDays }
    guard privateParent else { return nil }
    let config = settingsURL(databaseURL: databaseURL)
    let descriptor = Darwin.open(config.path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
    guard descriptor >= 0 else { return errno == ENOENT ? defaultDays : nil }
    defer { _ = Darwin.close(descriptor) }
    var pinned = stat()
    guard fstat(descriptor, &pinned) == 0,
          privateFile(pinned), pinned.st_size <= 128 else { return nil }
    let data = FileHandle(fileDescriptor: descriptor, closeOnDealloc: false).readDataToEndOfFile()
    var after = stat()
    guard lstat(config.path, &after) == 0, privateFile(after),
          after.st_dev == pinned.st_dev, after.st_ino == pinned.st_ino,
          let object = try? JSONSerialization.jsonObject(with: data),
          let dictionary = object as? [String: Any],
          dictionary.count == 1,
          let days = dictionary["retention_days"] as? Int,
          // Reject booleans, which bridge into NSNumber integers in JSON.
          !(dictionary["retention_days"] is Bool),
          allowedDays.contains(days) else { return nil }
    return days
  }

  // Save only the retention choice; never create the history database.
  static func saveDays(
    _ days: Int,
    databaseURL: URL = RecentScanHistoryReader.defaultDatabaseURL
  ) -> Bool {
    guard databaseURL.isFileURL, allowedDays.contains(days) else { return false }
    let parent = databaseURL.deletingLastPathComponent()
    if privateDirectory(parent) == nil {
      do {
        try FileManager.default.createDirectory(
          at: parent, withIntermediateDirectories: true,
          attributes: [.posixPermissions: 0o700])
      } catch { return false }
    }
    guard privateDirectory(parent) == true else { return false }
    let config = settingsURL(databaseURL: databaseURL)
    var previous = stat()
    if lstat(config.path, &previous) == 0 {
      guard privateFile(previous) else { return false }
    } else if errno != ENOENT {
      return false
    }
    guard let data = try? JSONSerialization.data(
      withJSONObject: ["retention_days": days], options: [.sortedKeys]
    ) else { return false }
    do {
      try data.write(to: config, options: .atomic)
    } catch { return false }
    guard chmod(config.path, 0o600) == 0 else { return false }
    return selectedDays(databaseURL: databaseURL) == days
  }

  // Automatically run when the enabled history page opens, on refresh and
  // after changes. Absent history stays absent; no PDF or operational cache
  // is read or deleted. The native scanner's authorization path is untouched.
  static func removeExpired(
    databaseURL: URL = RecentScanHistoryReader.defaultDatabaseURL,
    now: Date = Date()
  ) -> ScanHistoryExpiryOutcome {
    guard let days = selectedDays(databaseURL: databaseURL),
          now.timeIntervalSince1970.isFinite, now.timeIntervalSince1970 >= 0,
          privateDirectory(databaseURL.deletingLastPathComponent()) != false else {
      return .unavailable
    }
    let parent = databaseURL.deletingLastPathComponent()
    guard privateDirectory(parent) == true else { return .nothingToRemove }
    let resolvedParent = parent.resolvingSymlinksInPath()
    guard privateDirectory(resolvedParent) == true else { return .unavailable }
    let resolvedDatabase = resolvedParent.appendingPathComponent(databaseURL.lastPathComponent)
    var original = stat()
    guard lstat(resolvedDatabase.path, &original) == 0 else {
      return errno == ENOENT ? .nothingToRemove : .unavailable
    }
    guard privateFile(original) else { return .unavailable }
    let descriptor = Darwin.open(
      resolvedDatabase.path, O_RDWR | O_NOFOLLOW | O_CLOEXEC
    )
    guard descriptor >= 0 else { return .unavailable }
    defer { _ = Darwin.close(descriptor) }
    var pinned = stat()
    guard fstat(descriptor, &pinned) == 0, privateFile(pinned),
          original.st_dev == pinned.st_dev, original.st_ino == pinned.st_ino else {
      return .unavailable
    }
    func sameFile() -> Bool {
      var current = stat()
      return lstat(resolvedDatabase.path, &current) == 0
        && privateFile(current)
        && current.st_dev == pinned.st_dev && current.st_ino == pinned.st_ino
    }
    guard sameFile() else { return .unavailable }
    var opened: OpaquePointer?
    let flags = SQLITE_OPEN_READWRITE | SQLITE_OPEN_FULLMUTEX
    guard sqlite3_open_v2(resolvedDatabase.path, &opened, flags, nil) == SQLITE_OK,
          let database = opened else {
      if let opened { sqlite3_close(opened) }
      return .unavailable
    }
    defer { sqlite3_close(database) }
    guard sameFile(), sqlite3_db_readonly(database, "main") == 0,
          sqlite3_exec(database, "PRAGMA trusted_schema = OFF", nil, nil, nil) == SQLITE_OK,
          RecentScanHistoryReader.hasExactSchema(database),
          sqlite3_exec(database, "BEGIN IMMEDIATE", nil, nil, nil) == SQLITE_OK else {
      return .unavailable
    }
    var committed = false
    defer {
      if !committed { _ = sqlite3_exec(database, "ROLLBACK", nil, nil, nil) }
    }
    guard sameFile() else { return .unavailable }
    var statement: OpaquePointer?
    let sql = "DELETE FROM scan_history WHERE scanned_at < ?"
    guard sqlite3_prepare_v2(database, sql, -1, &statement, nil) == SQLITE_OK,
          let statement else { return .unavailable }
    let cutoff = now.timeIntervalSince1970 - Double(days) * 86400
    let bound = sqlite3_bind_double(statement, 1, cutoff) == SQLITE_OK
    let deleted = bound && sqlite3_step(statement) == SQLITE_DONE
    _ = sqlite3_finalize(statement)
    guard deleted, sameFile() else { return .unavailable }
    let count = Int(sqlite3_changes(database))
    guard sqlite3_exec(database, "COMMIT", nil, nil, nil) == SQLITE_OK else {
      return .unavailable
    }
    committed = true
    return count == 0 ? .nothingToRemove : .removed(count)
  }
}
