import Foundation

@main
struct TestFirstRunInstallationHealth {
  static func main() {
    typealias Health = FirstRunInstallationHealth

    let good = Health.assess(handlerInstalled: true,
                             signatureFiles: .present,
                             pdfAssociation: .opener)
    precondition(good.summary.contains("not a verified scan"))
    precondition(good.handlerDetail.contains("bundle identity"))
    precondition(good.signatureDetail.contains("validity and freshness are not checked"))
    precondition(good.associationDetail.contains("currently routes PDFs"))

    for signature in [Health.SignatureFiles.missing, .incomplete, .unsafe] {
      let status = Health.assess(handlerInstalled: true,
                                 signatureFiles: signature,
                                 pdfAssociation: .opener)
      precondition(status.summary.contains("missing or unverifiable"))
      precondition(!status.signatureDetail.isEmpty)
    }

    let absent = Health.assess(handlerInstalled: false,
                               signatureFiles: .present,
                               pdfAssociation: .opener)
    precondition(absent.summary.contains("missing or unverifiable"))
    precondition(absent.handlerDetail.contains("missing or cannot be verified"))

    for association in [Health.PDFAssociation.anotherApplication, .unknown] {
      let status = Health.assess(handlerInstalled: true,
                                 signatureFiles: .present,
                                 pdfAssociation: association)
      precondition(status.summary.contains("not confirmed"))
      precondition(status.associationDetail.contains("No association was changed.") ||
                   status.associationDetail.contains("no association was changed."))
    }

    precondition(Health.caveat.contains("does not run ClamAV"))
    precondition(Health.caveat.contains("native scan gate remains mandatory"))
    precondition(!good.summary.contains("safe to open"))
    print("First-run basic installation health fixtures passed")
  }
}
