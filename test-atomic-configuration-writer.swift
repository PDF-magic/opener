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

    // An independent process must not enter save while the destination lock
    // is held. A ready pipe makes the test deterministic before checking.
    let heldLock = open(lockPath.path, O_RDWR | O_NOFOLLOW | O_CLOEXEC)
    assert(heldLock >= 0)
    assert(flock(heldLock, LOCK_EX) == 0)
    var readyPipe: [Int32] = [0, 0]
    assert(pipe(&readyPipe) == 0)
    let child = fork()
    assert(child >= 0)
    if child == 0 {
      close(readyPipe[0])
      close(heldLock)
      var signal: UInt8 = 1
      guard Darwin.write(readyPipe[1], &signal, 1) == 1 else { _exit(2) }
      close(readyPipe[1])
      do {
        try AtomicConfigurationWriter.save(first, in: root, named: "settings.json")
        _exit(0)
      } catch {
        _exit(3)
      }
    }
    close(readyPipe[1])
    var signal: UInt8 = 0
    assert(Darwin.read(readyPipe[0], &signal, 1) == 1 && signal == 1)
    close(readyPipe[0])
    usleep(200_000)
    var childStatus: Int32 = 0
    assert(waitpid(child, &childStatus, WNOHANG) == 0)
    let lockedSnapshot = try Data(contentsOf: target)
    assert(lockedSnapshot == second)
    assert(flock(heldLock, LOCK_UN) == 0)
    close(heldLock)
    assert(waitpid(child, &childStatus, 0) == child && childStatus == 0)
    let unlockedSnapshot = try Data(contentsOf: target)
    assert(unlockedSnapshot == first)

    // Contending processes publish entire snapshots, never mixed bytes.
    let payloads = (0..<4).map { number in
      Data(repeating: UInt8(65 + number), count: 65_536)
    }
    var children: [pid_t] = []
    for payload in payloads {
      let pid = fork()
      assert(pid >= 0)
      if pid == 0 {
        do {
          for _ in 0..<12 {
            try AtomicConfigurationWriter.save(payload, in: root, named: "settings.json")
          }
          _exit(0)
        } catch {
          _exit(4)
        }
      }
      children.append(pid)
    }
    for pid in children {
      var status: Int32 = 0
      assert(waitpid(pid, &status, 0) == pid && status == 0)
    }
    let finalSnapshot = try Data(contentsOf: target)
    assert(payloads.contains(finalSnapshot))

    let names = try FileManager.default.contentsOfDirectory(atPath: root.path)
    assert(!names.contains(where: { $0.hasSuffix(".tmp") }))
    print("Atomic configuration saving tests passed")
  }
}
