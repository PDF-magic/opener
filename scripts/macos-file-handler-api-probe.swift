// Compile-only macOS file-handler SDK surface probe (opener-1167).
// This function is never called. Do not set the user's default applications here.
import AppKit
import CoreServices
import UniformTypeIdentifiers

@available(macOS 12.0, *)
func verifyFileHandlerSDK(document: URL, application: URL) {
    let workspace = NSWorkspace.shared
    _ = UTType.pdf.identifier
    _ = LSCopyDefaultRoleHandlerForContentType(UTType.pdf.identifier as CFString, .all)
    _ = workspace.urlForApplication(withBundleIdentifier: "com.brave.Browser")
    _ = workspace.urlsForApplications(withBundleIdentifier: "com.brave.Browser")
    _ = workspace.urlsForApplications(toOpen: UTType.pdf)
    _ = workspace.urlForApplication(toOpen: document)
    let configuration = NSWorkspace.OpenConfiguration()
    workspace.setDefaultApplication(at: application, toOpen: UTType.pdf) { _ in }
    workspace.open([document], withApplicationAt: application, configuration: configuration) { _, _ in }
    workspace.openApplication(at: application, configuration: configuration) { _, _ in }
    _ = workspace.open(document)
}
