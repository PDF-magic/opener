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
    assert(try Data(contentsOf: target) == first)
    try AtomicConfigurationWriter.save(second, in: root, named: "settings.json")
    assert(try Data(contentsOf: target) == second)

    // Invalid destination names must leave the last complete version intact.
    for name in ["", ".", "..", "../escape", "sub/name"] {
      do {
        try AtomicConfigurationWriter.save(first, in: root, named: name)
        fatalError("accepted unsafe file name")
      } catch AtomicConfigurationWriter.SaveError.invalidName {}
    }
    assert(try Data(contentsOf: target) == second)

    let link = root.appendingPathComponent("linked.json")
    try FileManager.default.createSymbolicLink(at: link, withDestinationURL: target)
    do {
      try AtomicConfigurationWriter.save(first, in: root, named: "linked.json")
      fatalError("accepted symlink destination")
    } catch AtomicConfigurationWriter.SaveError.unsafeDestination {}
    assert(try Data(contentsOf: target) == second)

    let missing = root.appendingPathComponent("missing", isDirectory: true)
    do {
      try AtomicConfigurationWriter.save(first, in: missing, named: "settings.json")
      fatalError("accepted missing directory")
    } catch AtomicConfigurationWriter.SaveError.unsafeDirectory {}
    assert(try Data(contentsOf: target) == second)

    let empty = Data()
    try AtomicConfigurationWriter.save(empty, in: root, named: "empty.json")
    assert(try Data(contentsOf: root.appendingPathComponent("empty.json")) == empty)
    let names = try FileManager.default.contentsOfDirectory(atPath: root.path)
    assert(!names.contains(where: { $0.hasSuffix(".tmp") }))
    print("Atomic configuration saving tests passed")
  }
}
