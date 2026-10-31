import Foundation

// A read-only first-run *installation inventory*. These facts are not a
// malware verdict or authorization to open a PDF; the installed scan handler
// independently validates the scanner, signatures, quarantine and file.
struct FirstRunInstallationHealth: Equatable {
  enum SignatureFiles: Equatable {
    case present
    case missing
    case incomplete
    case unsafe
  }

  enum PDFAssociation: Equatable {
    case opener
    case anotherApplication
    case unknown
  }

  let handlerInstalled: Bool
  let signatureFiles: SignatureFiles
  let pdfAssociation: PDFAssociation

  static func assess(
    handlerInstalled: Bool,
    signatureFiles: SignatureFiles,
    pdfAssociation: PDFAssociation
  ) -> Self {
    Self(handlerInstalled: handlerInstalled,
         signatureFiles: signatureFiles,
         pdfAssociation: pdfAssociation)
  }

  var summary: String {
    if !handlerInstalled || signatureFiles != .present {
      return "Basic installation check found missing or unverifiable components. See the results below before relying on PDF Magic Opener."
    }
    if pdfAssociation != .opener {
      return "Basic files were found, but PDF Magic Opener is not confirmed as your macOS default PDF handler. You can keep another default."
    }
    return "Basic components and PDF association were found. This is not a verified scan or a guarantee of protection."
  }

  var handlerDetail: String {
    handlerInstalled
      ? "The installed PDF Magic Opener scan-handler app was found with the expected bundle identity, PDF declaration, and executable."
      : "The installed PDF Magic Opener scan-handler app is missing or cannot be verified. Reinstall or repair it before using it to open PDFs."
  }

  var signatureDetail: String {
    switch signatureFiles {
    case .present:
      return "Main and daily ClamAV definition files were found; their validity and freshness are not checked here."
    case .missing:
      return "ClamAV definition files were not found. Install and update definitions before opening PDFs."
    case .incomplete:
      return "ClamAV definition files are incomplete. Update definitions before opening PDFs."
    case .unsafe:
      return "The ClamAV definition location could not be checked safely. Scanner protections remain enforced."
    }
  }

  var associationDetail: String {
    switch pdfAssociation {
    case .opener:
      return "macOS currently routes PDFs to the PDF Magic Opener handler."
    case .anotherApplication:
      return "Another application is the macOS PDF default. This is optional; no association was changed."
    case .unknown:
      return "The macOS PDF default could not be determined. No association was changed."
    }
  }

  static let caveat =
    "This checks only installation metadata. It does not run ClamAV, verify scanner versions or signature freshness, scan a PDF, or approve opening. The native scan gate remains mandatory."
}
