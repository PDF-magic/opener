import Foundation
import Darwin
import SQLite3

@main
struct ScanHistoryRetentionTests {
  static func require(_ ok: Bool, _ message: String) {
    precondition(ok, message)
  }

  static func count(_ database: OpaquePointer, _ sql: String) -> Int32 {
    var statement: OpaquePointer?
    require(sqlite3_prepare_v2(database, sql, -1, &statement, nil) == SQLITE_OK,
            "Could not prepare synthetic history query")
    defer { sqlite3_finalize(statement) }
    require(sqlite3_step(statement) == SQLITE_ROW, "Could not count synthetic entries")
    return sqlite3_column_int(statement, 0)
  }

  static func main() throws {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(
      "retention-tests-\(UUID().uuidString)", isDirectory: true)
    let folder = root.appendingPathComponent("scan-history", isDirectory: true)
    let db = folder.appendingPathComponent("scan-history.sqlite3")
    let config = folder.appendingPathComponent("retention.json")
    let unrelated = root.appendingPathComponent("clean-cache")
    try FileManager.default.createDirectory(
      at: root, withIntermediateDirectories: false,
      attributes: [.posixPermissions: 0o700])
    defer { try? FileManager.default.removeItem(at: root) }
    try "do not change".write(to: unrelated, atomically: false, encoding: .utf8)

    require(ScanHistoryRetentionStore.selectedDays(databaseURL: db) == 30,
            "Missing setting should default to 30 days")
    if case .nothingToRemove = ScanHistoryRetentionStore.removeExpired(databaseURL: db) {
    } else { fatalError("Missing optional history must be a no-op") }
    require(!FileManager.default.fileExists(atPath: folder.path),
            "Cleanup cannot create a history directory")

    require(!ScanHistoryRetentionStore.saveDays(0, databaseURL: db),
            "Unsupported retention must be rejected")
    require(ScanHistoryRetentionStore.saveDays(90, databaseURL: db),
            "A valid choice should persist")
    require(ScanHistoryRetentionStore.selectedDays(databaseURL: db) == 90,
            "Saved selection must round trip")
    require(!FileManager.default.fileExists(atPath: db.path),
            "Retention settings cannot enable collection or create SQLite")
    var configStat = stat()
    require(lstat(config.path, &configStat) == 0 && (configStat.st_mode & 0o777) == 0o600,
            "Retention preference must be private")

    var handle: OpaquePointer?
    require(sqlite3_open_v2(db.path, &handle,
                            SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, nil) == SQLITE_OK,
            "Could not build synthetic private history")
    guard let writer = handle else { fatalError("No SQLite handle") }
    let setup = """
      CREATE TABLE scan_history (id INTEGER PRIMARY KEY, scanned_at REAL NOT NULL,
      final_status TEXT NOT NULL, scanner_version TEXT,
      protection_profile_id TEXT NOT NULL);
      INSERT INTO scan_history(scanned_at,final_status,scanner_version,protection_profile_id)
      VALUES (1789990000,'clean','1.5.0','built-in');
      INSERT INTO scan_history(scanned_at,final_status,scanner_version,protection_profile_id)
      VALUES (1799000000,'scanFailed','1.5.0','built-in');
      INSERT INTO scan_history(scanned_at,final_status,scanner_version,protection_profile_id)
      VALUES (1800000000,'clean',NULL,'built-in');
      """
    require(sqlite3_exec(writer, setup, nil, nil, nil) == SQLITE_OK, "Could not insert fixtures")
    require(sqlite3_close(writer) == SQLITE_OK, "Could not close writer")
    require(chmod(db.path, 0o600) == 0, "Could not set private SQLite mode")

    let now = Date(timeIntervalSince1970: 1_800_000_000)
    switch ScanHistoryRetentionStore.removeExpired(databaseURL: db, now: now) {
    case .removed(let number):
      require(number == 1, "90-day expiry must remove just the oldest row")
    default: fatalError("Expected automatic cleanup of one expired row")
    }
    var read: OpaquePointer?
    require(sqlite3_open_v2(db.path, &read, SQLITE_OPEN_READONLY, nil) == SQLITE_OK,
            "Could not inspect synthetic results")
    guard let reader = read else { fatalError("No reader") }
    require(count(reader, "SELECT COUNT(*) FROM scan_history") == 2, "Must keep recent rows")
    require(sqlite3_close(reader) == SQLITE_OK, "Could not close reader")

    require(ScanHistoryRetentionStore.saveDays(7, databaseURL: db),
            "Changing retention must persist")
    switch ScanHistoryRetentionStore.removeExpired(databaseURL: db, now: now) {
    case .removed(let number):
      require(number == 1, "Shorter retention must immediately expire older rows")
    default: fatalError("Expected shorter-retention cleanup")
    }
    var still: OpaquePointer?
    require(sqlite3_open_v2(db.path, &still, SQLITE_OPEN_READONLY, nil) == SQLITE_OK,
            "Could not inspect remaining row")
    guard let remaining = still else { fatalError("No remaining handle") }
    require(count(remaining, "SELECT COUNT(*) FROM scan_history") == 1,
            "Must preserve last recent scan")
    require(sqlite3_close(remaining) == SQLITE_OK, "Could not close remaining handle")

    require(chmod(config.path, 0o644) == 0, "Could not construct unsafe config")
    require(ScanHistoryRetentionStore.selectedDays(databaseURL: db) == nil,
            "Nonprivate config must be rejected")
    if case .unavailable = ScanHistoryRetentionStore.removeExpired(databaseURL: db, now: now) {
    } else { fatalError("Unsafe config must block deletion") }
    require(chmod(config.path, 0o600) == 0, "Could not restore config mode")
    let outside = root.appendingPathComponent("outside")
    try "keep outside".write(to: outside, atomically: false, encoding: .utf8)
    try FileManager.default.removeItem(at: config)
    try FileManager.default.createSymbolicLink(at: config, withDestinationURL: outside)
    require(ScanHistoryRetentionStore.selectedDays(databaseURL: db) == nil,
            "Symlink config must fail closed")
    require(!ScanHistoryRetentionStore.saveDays(30, databaseURL: db),
            "Must not replace an untrusted settings symlink")
    require(try String(contentsOf: outside, encoding: .utf8) == "keep outside",
            "Unrelated content must remain unchanged")
    print("PASS: configured scan history retention prunes only expired private metadata")
  }
}
