import Foundation
import SQLite3
import Darwin

@main
struct ClearScanHistoryTests {
  static func matches(_ actual: ClearScanHistoryOutcome, _ expected: ClearScanHistoryOutcome) {
    switch (actual, expected) {
    case (.cleared, .cleared), (.nothingToClear, .nothingToClear),
         (.unavailable, .unavailable): return
    default: fatalError("Unexpected clear-history result")
    }
  }

  static func main() throws {
    let temp = FileManager.default.temporaryDirectory.appendingPathComponent(
      "test-clear-history-\(UUID().uuidString)", isDirectory: true)
    let folder = temp.appendingPathComponent("scan-history", isDirectory: true)
    let db = folder.appendingPathComponent("scan-history.sqlite3")
    let outside = temp.appendingPathComponent("operational-cache")
    try FileManager.default.createDirectory(at: temp, withIntermediateDirectories: false,
                                            attributes: [.posixPermissions: 0o700])
    defer { try? FileManager.default.removeItem(at: temp) }
    try "keep operational settings".write(to: outside, atomically: false, encoding: .utf8)

    matches(ClearScanHistoryStore.clear(databaseURL: db), .nothingToClear)
    precondition(!FileManager.default.fileExists(atPath: folder.path))

    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: false,
                                            attributes: [.posixPermissions: 0o700])
    matches(ClearScanHistoryStore.clear(databaseURL: db), .nothingToClear)

    var handle: OpaquePointer?
    precondition(sqlite3_open_v2(db.path, &handle,
                SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, nil) == SQLITE_OK)
    guard let database = handle else { fatalError("Could not create synthetic database") }
    precondition(sqlite3_exec(database,
      "CREATE TABLE scan_history (id INTEGER PRIMARY KEY, scanned_at REAL NOT NULL, final_status TEXT NOT NULL, scanner_version TEXT, protection_profile_id TEXT NOT NULL)", nil, nil, nil) == SQLITE_OK)
    precondition(sqlite3_exec(database,
      "INSERT INTO scan_history (scanned_at, final_status, scanner_version, protection_profile_id) VALUES (1700000000, 'clean', '1.5.0', 'built-in')", nil, nil, nil) == SQLITE_OK)
    precondition(sqlite3_close(database) == SQLITE_OK)
    precondition(chmod(db.path, 0o600) == 0)

    // These are synthetic SQLite sidecars, not real user data.
    for suffix in ["-wal", "-shm", "-journal"] {
      let sidecar = folder.appendingPathComponent("scan-history.sqlite3\(suffix)")
      try "synthetic".write(to: sidecar, atomically: false, encoding: .utf8)
      precondition(chmod(sidecar.path, 0o600) == 0)
    }
    let unrelated = folder.appendingPathComponent("other-app-data")
    try "unrelated".write(to: unrelated, atomically: false, encoding: .utf8)

    matches(ClearScanHistoryStore.clear(databaseURL: db), .cleared)
    for filename in ["scan-history.sqlite3", "scan-history.sqlite3-wal",
                     "scan-history.sqlite3-shm", "scan-history.sqlite3-journal"] {
      precondition(!FileManager.default.fileExists(atPath:
        folder.appendingPathComponent(filename).path))
    }
    precondition(try String(contentsOf: unrelated, encoding: .utf8) == "unrelated")
    precondition(try String(contentsOf: outside, encoding: .utf8) == "keep operational settings")
    matches(ClearScanHistoryStore.clear(databaseURL: db), .nothingToClear)
    precondition(!FileManager.default.fileExists(atPath: db.path))

    // A malicious alias must never delete its target or another file.
    try FileManager.default.createSymbolicLink(at: db, withDestinationURL: outside)
    matches(ClearScanHistoryStore.clear(databaseURL: db), .unavailable)
    precondition(try String(contentsOf: outside, encoding: .utf8) == "keep operational settings")
    try FileManager.default.removeItem(at: db)

    try "private".write(to: db, atomically: false, encoding: .utf8)
    precondition(chmod(db.path, 0o644) == 0)
    matches(ClearScanHistoryStore.clear(databaseURL: db), .unavailable)
    precondition(FileManager.default.fileExists(atPath: db.path))
    precondition(chmod(db.path, 0o600) == 0)

    // A malicious sidecar stops the entire operation, not just that entry.
    let sidecar = folder.appendingPathComponent("scan-history.sqlite3-wal")
    try FileManager.default.createSymbolicLink(at: sidecar, withDestinationURL: outside)
    matches(ClearScanHistoryStore.clear(databaseURL: db), .unavailable)
    precondition(FileManager.default.fileExists(atPath: db.path))
    precondition(try String(contentsOf: outside, encoding: .utf8) == "keep operational settings")
    try FileManager.default.removeItem(at: sidecar)

    precondition(chmod(folder.path, 0o755) == 0)
    matches(ClearScanHistoryStore.clear(databaseURL: db), .unavailable)
    precondition(FileManager.default.fileExists(atPath: db.path))
    precondition(chmod(folder.path, 0o700) == 0)
    matches(ClearScanHistoryStore.clear(databaseURL: db), .cleared)
    precondition(!FileManager.default.fileExists(atPath: db.path))
    print("PASS: confirmed history clearing removes only private SQLite history artifacts")
  }
}
