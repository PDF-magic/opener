import AppKit
import UniformTypeIdentifiers

guard let brave = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.brave.Browser") else {
    fputs("Brave Browser is not installed.\n", stderr)
    exit(1)
}

let handler = CommandLine.arguments.count > 1 ? URL(fileURLWithPath: CommandLine.arguments[1]) : brave
NSWorkspace.shared.setDefaultApplication(at: handler, toOpen: .pdf) { error in
    if let error = error {
        fputs("Could not set the PDF default handler: \(error.localizedDescription)\n", stderr)
        exit(1)
    }
    print("PDF opening uses \(handler.lastPathComponent).")
    exit(0)
}
RunLoop.main.run()
