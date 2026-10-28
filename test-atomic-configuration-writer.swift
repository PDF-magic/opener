import Darwin
import Foundation

@main
struct AtomicConfigurationWriterTests {
  static func main() throws {
    let arguments = CommandLine.arguments
    if arguments.count == 4 && arguments[1] == "--save-child" {
      let directory = URL(fileURLWithPath: arguments[2], isDirectory: true)
      FileHandle.standardOutput.write(Data([1]))
      try AtomicConfigurationWriter.save(Data(arguments[3].utf8), in: directory, named: "settings.json")
      return
    }
    if arguments.count == 4 && arguments[1] == "--batch-child" {
      let directory = URL(fileURLWithPath: arguments[2], isDirectory: true)
      guard let index = Int(arguments[3]), (0..<4).contains(index) else {
        fatalError("invalid test worker index")
      }
      let payload = Data(repeating: UInt8(65 + index), count: 65_536)
      for _ in 0..<12 {
        try AtomicConfigurationWriter.save(payload, in: directory, named: "settings.json")
      }
      return
    }

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

    // A lock remains on disk with owner-only permissions for later processes.
    let lockPath = root.appendingPathComponent(".settings.json.lock")
    assert(lstat(lockPath.path, &permissions) == 0)
    assert((permissions.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG))
    assert((permissions.st_mode & mode_t(0o7777)) == mode_t(0o600))

    // Refuse symlinks and directories masquerading as lock files.
    let symlinkLock = root.appendingPathComponent(".symlink-locked.json.lock")
    try FileManager.default.createSymbolicLink(at: symlinkLock, withDestinationURL: target)
    do {
      try AtomicConfigurationWriter.save(first, in: root, named: "symlink-locked.json")
      fatalError("accepted a symlink lock")
    } catch AtomicConfigurationWriter.SaveError.unsafeLock {}
    let directoryLock = root.appendingPathComponent(".directory-locked.json.lock")
    try FileManager.default.createDirectory(at: directoryLock, withIntermediateDirectories: false)
    do {
      try AtomicConfigurationWriter.save(first, in: root, named: "directory-locked.json")
      fatalError("accepted a directory lock")
    } catch AtomicConfigurationWriter.SaveError.unsafeLock {}

    // A separate executable invocation cannot finish saving while a different
    // process holds the destination lock. A one-byte signal ensures the worker
    // has started before testing contention.
    let heldLock = open(lockPath.path, O_RDWR | O_NOFOLLOW | O_CLOEXEC)
    assert(heldLock >= 0)
    assert(flock(heldLock, LOCK_EX) == 0)
    let executable = URL(fileURLWithPath: CommandLine.arguments[0])
    let child = Process()
    child.executableURL = executable
    child.arguments = ["--save-child", root.path, String(decoding: first, as: UTF8.self)]
    let readyPipe = Pipe()
    child.standardOutput = readyPipe
    try child.run()
    let ready = readyPipe.fileHandleForReading.readData(ofLength: 1)
    assert(ready == Data([1]))
    usleep(200_000)
    assert(child.isRunning)
    let lockedSnapshot = try Data(contentsOf: target)
    assert(lockedSnapshot == second)
    assert(flock(heldLock, LOCK_UN) == 0)
    close(heldLock)
    child.waitUntilExit()
    assert(child.terminationStatus == 0)
    let unlockedSnapshot = try Data(contentsOf: target)
    assert(unlockedSnapshot == first)

    // Contending independent processes publish complete snapshots, never
    // mixed bytes. Each worker writes many times to the same destination.
    let payloads = (0..<4).map { number in
      Data(repeating: UInt8(65 + number), count: 65_536)
    }
    var workers: [Process] = []
    for index in 0..<payloads.count {
      let worker = Process()
      worker.executableURL = executable
      worker.arguments = ["--batch-child", root.path, String(index)]
      try worker.run()
      workers.append(worker)
    }
    for worker in workers {
      worker.waitUntilExit()
      assert(worker.terminationStatus == 0)
    }
    let finalSnapshot = try Data(contentsOf: target)
    assert(payloads.contains(finalSnapshot))

    let names = try FileManager.default.contentsOfDirectory(atPath: root.path)
    assert(!names.contains(where: { $0.hasSuffix(".tmp") }))
    print("Atomic configuration saving tests passed")
  }
}
