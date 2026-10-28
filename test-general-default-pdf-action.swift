import Foundation

// No test may modify the runner's real PDF file associations.
@main
struct GeneralPDFDefaultActionTests {
  static func main() throws {
    let files = FileManager.default
    let root = files.temporaryDirectory.appendingPathComponent(
      "pdf-magic-settings-default-" + UUID().uuidString, isDirectory: true)
    try files.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? files.removeItem(at: root) }

    func makeBundle(_ directory: String, name: String = "PDF Magic Opener",
                    identifier: String = PDFDefaultApplicationAction.handlerBundleID,
                    executable: Bool = true, handlesPDF: Bool = true) throws -> URL {
      let app = root.appendingPathComponent(directory, isDirectory: true)
        .appendingPathComponent(name + ".app", isDirectory: true)
      let macOS = app.appendingPathComponent("Contents/MacOS", isDirectory: true)
      try files.createDirectory(at: macOS, withIntermediateDirectories: true)
      let info: [String: Any] = [
        "CFBundleIdentifier": identifier,
        "CFBundleExecutable": "PDFOpener",
        "CFBundlePackageType": "APPL",
        "CFBundleDocumentTypes": [[
          "LSItemContentTypes": [handlesPDF ? "com.adobe.pdf" : "public.plain-text"],
          "CFBundleTypeRole": "Viewer",
        ]],
      ]
      let data = try PropertyListSerialization.data(
        fromPropertyList: info, format: .xml, options: 0)
      try data.write(to: app.appendingPathComponent("Contents/Info.plist"))
      if executable {
        let binary = macOS.appendingPathComponent("PDFOpener")
        try "#!/bin/sh\nexit 0\n".write(to: binary, atomically: true, encoding: .utf8)
        try files.setAttributes([.posixPermissions: 0o755], ofItemAtPath: binary.path)
      }
      return app
    }

    let valid = try makeBundle("valid")
    let wrongID = try makeBundle("wrongID", identifier: "local.studio.pdfmagicopener.swiftui")
    let wrongName = try makeBundle("wrongName", name: "Other")
    let noPDF = try makeBundle("noPDF", handlesPDF: false)
    let noExecutable = try makeBundle("noExecutable", executable: false)
    let linkFolder = root.appendingPathComponent("link", isDirectory: true)
    try files.createDirectory(at: linkFolder, withIntermediateDirectories: true)
    let link = linkFolder.appendingPathComponent("PDF Magic Opener.app", isDirectory: true)
    try files.createSymbolicLink(at: link, withDestinationURL: valid)

    precondition(PDFDefaultApplicationAction.verifiedHandler(at: valid))
    for unsafe in [wrongID, wrongName, noPDF, noExecutable, link,
                   root.appendingPathComponent("missing/PDF Magic Opener.app")] {
      precondition(!PDFDefaultApplicationAction.verifiedHandler(at: unsafe),
                   "Invalid or unrelated bundle must never be registered")
    }

    var launches = 0
    var lookups = 0
    var succeeded: Bool?
    PDFDefaultApplicationAction.request(
      at: valid,
      runHelper: { app, finish in
        precondition(app == valid)
        launches += 1
        finish(true)
      },
      currentPDFHandler: {
        lookups += 1
        return PDFDefaultApplicationAction.handlerBundleID
      },
      completion: { succeeded = $0 })
    precondition(succeeded == true && launches == 1 && lookups == 1)

    PDFDefaultApplicationAction.request(
      at: wrongID,
      runHelper: { _, _ in launches += 1 },
      currentPDFHandler: { lookups += 1; return nil },
      completion: { succeeded = $0 })
    precondition(succeeded == false && launches == 1 && lookups == 1,
                 "Invalid app must never invoke a helper or read system state")

    PDFDefaultApplicationAction.request(
      at: valid,
      runHelper: { _, finish in launches += 1; finish(false) },
      currentPDFHandler: { lookups += 1; return PDFDefaultApplicationAction.handlerBundleID },
      completion: { succeeded = $0 })
    precondition(succeeded == false && launches == 2 && lookups == 1,
                 "Helper failure must not be reported as success")

    PDFDefaultApplicationAction.request(
      at: valid,
      runHelper: { _, finish in launches += 1; finish(true) },
      currentPDFHandler: { lookups += 1; return "com.apple.Preview" },
      completion: { succeeded = $0 })
    precondition(succeeded == false && launches == 3 && lookups == 2,
                 "A successful helper is not proof of a changed PDF association")
    print("PASS: General PDF default action verifies the installed scan handler and actual result.")
  }
}
