import AppKit
import Foundation
import UserNotifications

// Built with the installed PDF opener's real notification functions, but with
// only the macOS notification transport replaced by an in-memory fake. No
// permission prompts, Notification Center changes, scanners or user settings.
@main
struct NotificationsWhileMainAppClosedTests {
    final class DeliveryRecord {
        var permissionRequests = 0
        var scheduled = [UNNotificationRequest]()
        var finished = 0
    }

    static func check(
        status: UNAuthorizationStatus,
        authorizationGranted: Bool,
        kind: String,
        expectedNotice: String?,
        expectedPermissionRequests: Int = 0
    ) {
        let record = DeliveryRecord()
        let transport = NativeScanNotificationTransport(
            getAuthorizationStatus: { completion in completion(status) },
            requestAuthorization: { completion in
                record.permissionRequests += 1
                completion(authorizationGranted)
            },
            add: { request, completion in
                record.scheduled.append(request)
                completion()
            }
        )
        let finished = { record.finished += 1 }
        switch kind {
        case "success":
            deliverSuccessfulScanNotification(transport: transport, completion: finished)
        case "blocked":
            deliverBlockedFileNotification(malwareDetected: false, scanFailed: false, transport: transport, completion: finished)
        case "failed":
            deliverBlockedFileNotification(malwareDetected: false, scanFailed: true, transport: transport, completion: finished)
        case "malware":
            deliverBlockedFileNotification(malwareDetected: true, scanFailed: false, transport: transport, completion: finished)
        default:
            fatalError("Invalid test case")
        }
        precondition(record.finished == 1, "Every delivery path must finish exactly once")
        precondition(record.permissionRequests == expectedPermissionRequests,
                     "Do not request permission unless macOS reports it undetermined")
        precondition(record.scheduled.count == (expectedNotice == nil ? 0 : 1),
                     "Denied notices must never be scheduled")
        if let expectedNotice {
            let notice = record.scheduled[0]
            precondition(notice.content.title == "PDF Magic Opener")
            precondition(notice.content.body == expectedNotice,
                         "Notification text must be fixed and path-free")
            precondition(notice.trigger == nil)
        }
    }

    static func main() {
        // The Python integration runner explicitly launches and quits this
        // separate preferences app before starting this native-owner test.
        precondition(NSRunningApplication.runningApplications(
            withBundleIdentifier: "local.studio.pdfmagicopener.swiftui"
        ).isEmpty, "Notifications must work with the main preferences app closed")

        let suite = "local.studio.pdf-magic-opener.test.closed." + UUID().uuidString
        guard let defaults = UserDefaults(suiteName: suite) else {
            fatalError("Cannot create isolated notification settings")
        }
        defer { defaults.removePersistentDomain(forName: suite) }
        defaults.set("preserve-user-choice", forKey: "unrelatedPDFApplication")
        precondition(!SuccessfulScanNotificationPreference.isEnabled(defaults: defaults))
        precondition(!BlockedFileNotificationPreference.isEnabled(defaults: defaults))
        precondition(SuccessfulScanNotificationPreference.save(true, defaults: defaults))
        precondition(BlockedFileNotificationPreference.save(true, defaults: defaults))
        let reopened = UserDefaults(suiteName: suite)!
        precondition(SuccessfulScanNotificationPreference.isEnabled(defaults: reopened))
        precondition(BlockedFileNotificationPreference.isEnabled(defaults: reopened))

        let success = "A PDF passed scanning and was handed off to your chosen application."
        let blocked = "A PDF could not be opened because its safety check failed."
        let malware = "Malware was detected. The PDF was blocked and was not opened."
        let failed = "A PDF scan failed or could not finish. The file was not opened."
        // A closed preferences process must not prevent either opted-in notice.
        check(status: .authorized, authorizationGranted: false, kind: "success",
              expectedNotice: success)
        check(status: .provisional, authorizationGranted: false, kind: "blocked",
              expectedNotice: blocked)
        check(status: .authorized, authorizationGranted: false, kind: "failed",
              expectedNotice: failed)
        check(status: .authorized, authorizationGranted: false, kind: "malware",
              expectedNotice: malware)
        check(status: .notDetermined, authorizationGranted: true, kind: "success",
              expectedNotice: success, expectedPermissionRequests: 1)
        check(status: .notDetermined, authorizationGranted: false, kind: "blocked",
              expectedNotice: nil, expectedPermissionRequests: 1)
        for kind in ["success", "blocked", "failed", "malware"] {
            check(status: .denied, authorizationGranted: true, kind: kind, expectedNotice: nil)
        }

        // Even with the main UI closed, preferences, cancellation and scanner
        // verdicts decide eligibility; delivery never overrides those gates.
        precondition(!SuccessfulScanNotificationPreference.shouldNotify(
            failure: nil, cancelled: false, enabled: false))
        precondition(!SuccessfulScanNotificationPreference.shouldNotify(
            failure: "Scanner failed", cancelled: false, enabled: true))
        precondition(!SuccessfulScanNotificationPreference.shouldNotify(
            failure: nil, cancelled: true, enabled: true))
        precondition(BlockedFileNotificationPreference.notificationKind(
            failure: "Scan request 1: Malware was detected; opening was stopped.\n",
            cancelled: false, enabled: true) == .malwareDetected)
        precondition(BlockedFileNotificationPreference.notificationKind(
            failure: "Scan request 1: Malware was detected; opening was stopped.\n",
            cancelled: true, enabled: true) == .none)
        precondition(reopened.string(forKey: "unrelatedPDFApplication") == "preserve-user-choice")
        print("PASS: native notifications complete after the independent Settings app closes")
    }
}
