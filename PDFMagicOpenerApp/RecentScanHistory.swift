import Foundation
import Darwin
import SQLite3

// Read-only presentation of the optional metadata store defined by
// scan_history_metadata.py. Never open a document, infer a successful launch
// from a clean verdict, or create a database merely to populate the UI.
struct RecentScanHistoryRow: Identifiable {
  let id: Int64
  let scannedAt: Date
  let status: String
  let scannerVersion: String?
  let profile: String

  var statusLabel: String {
    switch status {
    case "clean": return "Clean scan (opening not verified)"
    case "malwareDetected": return "Malware detected"
    case "suspiciousStructure": return "Suspicious structure"
    case "encrypted": return "Encrypted document"
    case "incompleteScan": return "Incomplete scan"
    case "scanFailed": return "Scan failed"
    case "scanTimedOut": return "Scan timed out"
    case "fileChanged": return "File changed during scan"
    case "fileTooLarge": return "File too large"
    case "cancelled": return "Scan cancelled"
    default: return "Unknown result"
    }
  }
}

enum RecentScanHistoryLoad {
  case entries([RecentScanHistoryRow])
  case empty
  case unavailable
}

enum RecentScanHistoryReader {
  static let maximumResults = 20
  static let defaultDatabaseURL = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/Application Support/Studio/allow-and-open/scan-history/scan-history.sqlite3")

  private static let expectedColumns = [
    "id|INTEGER|0|1|0",
    "scanned_at|REAL|1|0|0",
    "final_status|TEXT|1|0|0",
    "scanner_version|TEXT|0|0|0",
    "protection_profile_id|TEXT|1|0|0"
  ]

  private static let statuses: Set<String> = [
    "clean", "malwareDetected", "suspiciousStructure", "encrypted",
    "incompleteScan", "scanFailed", "scanTimedOut", "fileChanged",
    "fileTooLarge", "cancelled"
  ]

  private static func readText(_ statement: OpaquePointer, column: Int32) -> String? {
    guard sqlite3_column_type(statement, column) == SQLITE_TEXT,
          let data = sqlite3_column_text(statement, column) else { return nil }
    return String(data: Data(bytes: data, count: Int(sqlite3_column_bytes(statement, column))),
                  encoding: .utf8)
  }

  private static func isPrivate(_ path: String, directory: Bool) -> Bool? {
    var metadata = stat()
    guard lstat(path, &metadata) == 0 else {
      return errno == ENOENT ? nil : false
    }
    let expectedType: mode_t = directory ? mode_t(S_IFDIR) : mode_t(S_IFREG)
    return (metadata.st_mode & mode_t(S_IFMT)) == expectedType
      && metadata.st_uid == getuid()
      && (metadata.st_mode & mode_t(0o077)) == 0
  }

  private static func hasExactSchema(_ database: OpaquePointer) -> Bool {
    var query: OpaquePointer?
    guard sqlite3_prepare_v2(database, "PRAGMA table_xinfo(scan_history)", -1,
                             &query, nil) == SQLITE_OK, let query else { return false }
    defer { sqlite3_finalize(query) }
    var columns: [String] = []
    var result = sqlite3_step(query)
    while result == SQLITE_ROW {
      guard let name = readText(query, column: 1),
            let type = readText(query, column: 2) else { return false }
      columns.append("\(name)|\(type.uppercased())|\(sqlite3_column_int(query, 3))|\(sqlite3_column_int(query, 5))|\(sqlite3_column_int(query, 6))")
      result = sqlite3_step(query)
    }
    return result == SQLITE_DONE && columns == expectedColumns
  }

  static func load(databaseURL: URL = defaultDatabaseURL) -> RecentScanHistoryLoad {
    // An absent optional store is normal. Do not create a directory, database,
    // SQLite journal, preference, or a history record just to display history.
    guard databaseURL.isFileURL else { return .unavailable }
    guard let parentPrivate = isPrivate(databaseURL.deletingLastPathComponent().path,
                                        directory: true) else { return .empty }
    guard parentPrivate else { return .unavailable }
    guard let filePrivate = isPrivate(databaseURL.path, directory: false) else { return .empty }
    guard filePrivate else { return .unavailable }

    // macOS temporary and home directories may have trusted symlinked
    // ancestors (for example /var -> /private/var). Resolve *only* the parent
    // directories, never the database filename. Revalidate the resolved owner
    // and permissions before SQLite opens the final component with NOFOLLOW.
    let resolvedParent = databaseURL.deletingLastPathComponent().resolvingSymlinksInPath()
    let resolvedDatabase = resolvedParent.appendingPathComponent(databaseURL.lastPathComponent)
    guard isPrivate(resolvedParent.path, directory: true) == true,
          isPrivate(resolvedDatabase.path, directory: false) == true else {
      return .unavailable
    }

    // Pin the already validated regular file through a kernel-level
    // O_NOFOLLOW read descriptor. SQLite's NOFOLLOW open flag can fail on
    // some macOS filesystem paths even for genuine private databases.
    let descriptor = Darwin.open(resolvedDatabase.path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
    guard descriptor >= 0 else { return .unavailable }
    defer { _ = Darwin.close(descriptor) }
    var pinned = stat()
    guard fstat(descriptor, &pinned) == 0,
          (pinned.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG),
          pinned.st_uid == getuid(),
          (pinned.st_mode & mode_t(0o077)) == 0 else { return .unavailable }
    func matchesPinnedFile() -> Bool {
      var current = stat()
      return lstat(resolvedDatabase.path, &current) == 0
        && (current.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG)
        && current.st_dev == pinned.st_dev && current.st_ino == pinned.st_ino
        && current.st_uid == pinned.st_uid
        && (current.st_mode & mode_t(0o077)) == 0
    }
    guard matchesPinnedFile() else { return .unavailable }

    var opened: OpaquePointer?
    // This SQLite connection is strictly read-only, cannot create the store,
    // and is never used by the scanner or document-opening authorization gate.
    let flags = SQLITE_OPEN_READONLY | SQLITE_OPEN_FULLMUTEX
    guard sqlite3_open_v2(resolvedDatabase.path, &opened, flags, nil) == SQLITE_OK,
          let database = opened else {
      if let opened { sqlite3_close(opened) }
      return .unavailable
    }
    defer { sqlite3_close(database) }
    guard matchesPinnedFile(), sqlite3_db_readonly(database, "main") == 1,
          hasExactSchema(database) else { return .unavailable }

    var query: OpaquePointer?
    let sql = "SELECT id, scanned_at, final_status, scanner_version, protection_profile_id "
      + "FROM scan_history ORDER BY scanned_at DESC, id DESC LIMIT 20"
    guard sqlite3_prepare_v2(database, sql, -1, &query, nil) == SQLITE_OK,
          let query else { return .unavailable }
    defer { sqlite3_finalize(query) }
    var rows: [RecentScanHistoryRow] = []
    var result = sqlite3_step(query)
    while result == SQLITE_ROW {
      let timeType = sqlite3_column_type(query, 1)
      let versionType = sqlite3_column_type(query, 3)
      let time = sqlite3_column_double(query, 1)
      guard sqlite3_column_type(query, 0) == SQLITE_INTEGER,
            (timeType == SQLITE_FLOAT || timeType == SQLITE_INTEGER),
            time.isFinite, time >= 0, time <= 253402300799,
            let status = readText(query, column: 2), statuses.contains(status),
            let profile = readText(query, column: 4), profile == "built-in",
            (versionType == SQLITE_NULL || versionType == SQLITE_TEXT) else {
        return .unavailable
      }
      let version = versionType == SQLITE_NULL ? nil : readText(query, column: 3)
      if versionType == SQLITE_TEXT {
        guard let version, version.utf8.count <= 64,
              version.range(of: #"^[0-9]+(?:\.[0-9]+){1,3}(?:[-+][A-Za-z0-9._-]+)?$"#,
                            options: .regularExpression) != nil else { return .unavailable }
      }
      rows.append(RecentScanHistoryRow(
        id: sqlite3_column_int64(query, 0),
        scannedAt: Date(timeIntervalSince1970: time),
        status: status, scannerVersion: version, profile: profile))
      result = sqlite3_step(query)
    }
    guard result == SQLITE_DONE else { return .unavailable }
    return rows.isEmpty ? .empty : .entries(rows)
  }
}
