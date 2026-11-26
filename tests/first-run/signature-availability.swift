import Foundation

@main
struct TestFirstRunSignatureAvailability {
  static func main() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("pdfmagic-first-run-signatures-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }

    let directory = root.appendingPathComponent("signatures", isDirectory: true)
    precondition(FirstRunSignatureAvailability.read(from: directory) == .missing)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
    precondition(FirstRunSignatureAvailability.read(from: directory) == .incomplete)

    let main = directory.appendingPathComponent("main.cvd")
    let daily = directory.appendingPathComponent("daily.cld")
    try Data("placeholder-main".utf8).write(to: main)
    precondition(FirstRunSignatureAvailability.read(from: directory) == .incomplete)
    try Data("placeholder-daily".utf8).write(to: daily)
    precondition(FirstRunSignatureAvailability.read(from: directory) == .available)
    let observedMain = try Data(contentsOf: main)
    let observedDaily = try Data(contentsOf: daily)
    precondition(observedMain == Data("placeholder-main".utf8))
    precondition(observedDaily == Data("placeholder-daily".utf8))

    let alternate = directory.appendingPathComponent("main.cld")
    try Data("alternate".utf8).write(to: alternate)
    precondition(FirstRunSignatureAvailability.read(from: directory) == .incomplete)
    try FileManager.default.removeItem(at: alternate)
    try Data().write(to: daily)
    precondition(FirstRunSignatureAvailability.read(from: directory) == .incomplete)
    try FileManager.default.removeItem(at: daily)

    // A symlink must not be treated as a legitimate signature file.
    try FileManager.default.createSymbolicLink(at: daily, withDestinationURL: main)
    precondition(FirstRunSignatureAvailability.read(from: directory) == .unsafe)
    try FileManager.default.removeItem(at: daily)
    try FileManager.default.createDirectory(at: daily, withIntermediateDirectories: false)
    precondition(FirstRunSignatureAvailability.read(from: directory) == .unsafe)
    try FileManager.default.removeItem(at: daily)

    let linked = root.appendingPathComponent("linked-signatures")
    try FileManager.default.createSymbolicLink(at: linked, withDestinationURL: directory)
    precondition(FirstRunSignatureAvailability.read(from: linked) == .unsafe)

    for result in [FirstRunSignatureAvailability.available, .missing, .incomplete, .unsafe] {
      precondition(!result.explanation.isEmpty)
      precondition(!result.explanation.contains(root.path))
    }
    print("First-run signature availability tests passed")
  }
}
