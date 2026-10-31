import Foundation
import SQLite3
import Darwin

@main
struct RecentScanHistoryTests {
  static func expectEmpty(_ result: RecentScanHistoryLoad, stage: String) {
    if case .empty = result { return }
    if case .unavailable = result {
      fatalError("Expected empty scan history at \(stage), got unavailable")
    }
    fatalError("Expected empty scan history at \(stage), got entries")
  }

  static func expectUnavailable(_ result: RecentScanHistoryLoad) {
    if case .unavailable = result { return }
    fatalError("Invalid or nonprivate history must fail closed")
  }

  static func execute(_ database: OpaquePointer, _ sql: String) {
    precondition(sqlite3_exec(database, sql, nil, nil, nil) == SQLITE_OK)
  }

  static func main() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("recent-scan-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false,
        attributes: [.posixPermissions: 0o700])
    defer { try? FileManager.default.removeItem(at: root) }

    let databaseURL = root.appendingPathComponent("scan-history.sqlite3")
    expectEmpty(RecentScanHistoryReader.load(databaseURL: databaseURL), stage: "database absent")
    precondition(!FileManager.default.fileExists(atPath: databaseURL.path))

    var database: OpaquePointer?
    precondition(sqlite3_open_v2(databaseURL.path, &database,
                                SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, nil) == SQLITE_OK)
    guard let database else { fatalError("Could not create synthetic history") }
    execute(database, "CREATE TABLE scan_history (id INTEGER PRIMARY KEY, scanned_at REAL NOT NULL, final_status TEXT NOT NULL, scanner_version TEXT, protection_profile_id TEXT NOT NULL)")
    precondition(sqlite3_close(database) == SQLITE_OK)
    precondition(chmod(databaseURL.path, 0o600) == 0)
    let version = String(cString: sqlite3_libversion())
    var probe: OpaquePointer?
    let probeCode = sqlite3_open_v2(databaseURL.path, &probe,
        SQLITE_OPEN_READONLY | SQLITE_OPEN_FULLMUTEX | SQLITE_OPEN_NOFOLLOW, nil)
    if probeCode != SQLITE_OK {
      fatalError("SQLite readonly/no-follow open failed (code \(probeCode), version \(version))")
    }
    if let probe { precondition(sqlite3_close(probe) == SQLITE_OK) }
    expectEmpty(RecentScanHistoryReader.load(databaseURL: databaseURL), stage: "empty canonical table")

    // Only synthetic metadata is inserted; never touch real user history.
    var writer: OpaquePointer?
    precondition(sqlite3_open_v2(databaseURL.path, &writer, SQLITE_OPEN_READWRITE, nil) == SQLITE_OK)
    guard let writer else { fatalError("Could not reopen synthetic history") }
    for i in 0..<25 {
      let status = i == 24 ? "scanFailed" : "clean"
      execute(writer, "INSERT INTO scan_history (scanned_at, final_status, scanner_version, protection_profile_id) VALUES (\(1700000000 + i), '\(status)', '1.5.0', 'built-in')")
    }
    precondition(sqlite3_close(writer) == SQLITE_OK)
    switch RecentScanHistoryReader.load(databaseURL: databaseURL) {
    case .entries(let rows):
      precondition(rows.count == 20, "Only the 20 newest entries may be shown")
      precondition(rows[0].status == "scanFailed")
      precondition(rows[0].statusLabel == "Scan failed")
      precondition(rows[1].statusLabel == "Clean scan (opening not verified)")
      precondition(rows[0].scannedAt.timeIntervalSince1970 == 1700000024)
      precondition(rows[0].scannerVersion == "1.5.0")
      precondition(rows[0].profile == "built-in")
    default:
      fatalError("Expected sorted, validated history results")
    }

    let alias = root.appendingPathComponent("alias.sqlite3")
    try FileManager.default.createSymbolicLink(at: alias, withDestinationURL: databaseURL)
    expectUnavailable(RecentScanHistoryReader.load(databaseURL: alias))
    precondition(chmod(databaseURL.path, 0o644) == 0)
    expectUnavailable(RecentScanHistoryReader.load(databaseURL: databaseURL))
    precondition(chmod(databaseURL.path, 0o600) == 0)

    var changed: OpaquePointer?
    precondition(sqlite3_open_v2(databaseURL.path, &changed, SQLITE_OPEN_READWRITE, nil) == SQLITE_OK)
    guard let corruptionDatabase = changed else {
      fatalError("Could not open synthetic history for corruption test")
    }
    execute(corruptionDatabase, "UPDATE scan_history SET final_status = 'unrecognized' WHERE id = 25")
    precondition(sqlite3_close(corruptionDatabase) == SQLITE_OK)
    expectUnavailable(RecentScanHistoryReader.load(databaseURL: databaseURL))

    changed = nil
    precondition(sqlite3_open_v2(databaseURL.path, &changed, SQLITE_OPEN_READWRITE, nil) == SQLITE_OK)
    guard let schemaDatabase = changed else { fatalError("Could not edit schema") }
    execute(schemaDatabase, "ALTER TABLE scan_history ADD COLUMN source_url TEXT")
    precondition(sqlite3_close(schemaDatabase) == SQLITE_OK)
    expectUnavailable(RecentScanHistoryReader.load(databaseURL: databaseURL))
    print("PASS: recent scan history is explicit, private, bounded, canonical, and read-only")
  }
}
