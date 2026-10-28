import Darwin
import Foundation

@main
struct AtomicConfigurationWriterTests {
  static func main() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("atomic-config-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
    defer { try? FileManager.default.removeItem(at: root) }
    let target = root.appendingPathComponent("settings.json")

    let first = Data(#"{"version":1,"value":"old"}"#.utf8)
    let second = Data(#"{"version":1,"value":"new"}"#.utf8)
    try AtomicConfigurationWriter.save(first, in: root, named: "settings.json")
    let firstRead = try Data(contentsOf: target)
    assert(firstRead == first)
    try AtomicConfigurationWriter.save(second, in: root, named: "settings.json")
    let secondRead = try Data(contentsOf: target)
    assert(secondRead == second)

    // Invalid destination names must leave the last complete version intact.
    for name in ["", ".", "..", "../escape", "sub/name"] {
      do {
        try AtomicConfigurationWriter.save(first, in: root, named: name)
        fatalError("accepted unsafe file name")
      } catch AtomicConfigurationWriter.SaveError.invalidName {}
    }
    let safetyRead = try Data(contentsOf: target)
    assert(safetyRead == second)

    let link = root.appendingPathComponent("linked.json")
    try FileManager.default.createSymbolicLink(at: link, withDestinationURL: target)
    do {
      try AtomicConfigurationWriter.save(first, in: root, named: "linked.json")
      fatalError("accepted symlink destination")
    } catch AtomicConfigurationWriter.SaveError.unsafeDestination {}
    let secondRead2 = try Data(contentsOf: target)
    assert(secondRead2 == second)

    let missing = root.appendingPathComponent("missing", isDirectory: true)
    do {
      try AtomicConfigurationWriter.save(first, in: missing, named: "settings.json")
      fatalError("accepted missing directory")
    } catch AtomicConfigurationWriter.SaveError.unsafeDirectory {}
    let secondRead3 = try Data(contentsOf: target)
    assert(secondRead3 == second)

    let empty = Data()
    try AtomicConfigurationWriter.save(empty, in: root, named: "empty.json")
    let emptyRead = try Data(contentsOf: root.appendingPathComponent("empty.json"))
    assert(emptyRead == empty)
    // A permissive process umask must not make configuration world-readable.
    let previousUmask = umask(0)
    defer { _ = umask(previousUmask) }
    try AtomicConfigurationWriter.save(first, in: root, named: "private.json")
    var permissions = stat()
    let privatePath = root.appendingPathComponent("private.json").path
    assert(lstat(privatePath, &permissions) == 0)
    assert((permissions.st_mode & mode_t(0o7777)) == mode_t(0o600))

    // Existing settings may have overly permissive legacy permissions.
    // Replacement must not retain those permissions or truncate on failure.
    assert(chmod(target.path, mode_t(0o644)) == 0)
    try AtomicConfigurationWriter.save(first, in: root, named: "settings.json")
    assert(lstat(target.path, &permissions) == 0)
    assert((permissions.st_mode & mode_t(0o7777)) == mode_t(0o600))
    let restrictedRead = try Data(contentsOf: target)
    assert(restrictedRead == first)

    // A locked-down legacy file is replaceable without first broadening it.
    assert(chmod(target.path, mode_t(0o000)) == 0)
    try AtomicConfigurationWriter.save(second, in: root, named: "settings.json")
    assert(lstat(target.path, &permissions) == 0)
    assert((permissions.st_mode & mode_t(0o7777)) == mode_t(0o600))
    let restoredRead = try Data(contentsOf: target)
    assert(restoredRead == second)

    let names = try FileManager.default.contentsOfDirectory(atPath: root.path)
    assert(!names.contains(where: { $0.hasSuffix(".tmp") }))
    print("Atomic configuration saving tests passed")
  }
}
