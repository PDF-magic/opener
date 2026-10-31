import Foundation

@main
struct NotificationDeduplicationTests {
  static func main() {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let alpha = "opaque-document-alpha.success"
    let beta = "opaque-document-beta.success"
    let blocked = "opaque-document-alpha.blocked"
    func canQueue(
      _ id: String,
      _ delivered: [(identifier: String, date: Date)] = [],
      _ pending: [String] = []
    ) -> Bool {
      ScanNotificationDeduplication.shouldQueue(
        identifier: id, delivered: delivered, pendingIdentifiers: pending, now: now)
    }

    precondition(canQueue(alpha), "First notification must be eligible")
    precondition(!canQueue(alpha, [], [alpha]), "Pending repeats must be dropped")
    precondition(canQueue(beta, [], [alpha]), "Another document must be independent")
    precondition(canQueue(blocked, [], [alpha]), "A different outcome must be independent")
    precondition(!canQueue(alpha, [(alpha, now.addingTimeInterval(-5))]),
                 "A recently delivered notice must be suppressed")
    precondition(canQueue(beta, [(alpha, now.addingTimeInterval(-5))]),
                 "Other documents must still notify")
    precondition(canQueue(alpha, [(alpha, now.addingTimeInterval(-31))]),
                 "A later explicit scan must notify after expiry")
    precondition(canQueue(alpha, [(alpha, now.addingTimeInterval(-30))]),
                 "The 30-second boundary is no longer suppressed")
    precondition(canQueue(alpha, [(alpha, now.addingTimeInterval(5))]),
                 "Future-dated notifications must not lock out new ones")
    precondition(!canQueue(alpha, [(alpha, now.addingTimeInterval(-1))], [alpha]),
                 "Both delivered and pending repeats are suppressed")

    let reservations = ScanNotificationReservation()
    precondition(reservations.reserve(alpha, now: now))
    precondition(!reservations.reserve(alpha, now: now.addingTimeInterval(1)))
    precondition(reservations.reserve(beta, now: now.addingTimeInterval(1)))
    precondition(reservations.reserve(blocked, now: now.addingTimeInterval(1)))
    precondition(reservations.reserve(alpha, now: now.addingTimeInterval(30)),
                 "After the suppression interval, a new scan may notify")
    precondition(!reservations.reserve(alpha, now: now.addingTimeInterval(30)),
                 "The new reservation must be exclusive")
    precondition(SuccessfulScanNotificationPreference.shouldNotify(
      failure: nil, cancelled: false, enabled: true))
    precondition(!SuccessfulScanNotificationPreference.shouldNotify(
      failure: nil, cancelled: true, enabled: true))
    precondition(BlockedFileNotificationPreference.notificationKind(
      failure: "scan denied", cancelled: false, enabled: true) == .blocked)
    precondition(BlockedFileNotificationPreference.notificationKind(
      failure: "scan denied", cancelled: true, enabled: true) == .none)
    print("PASS: identical notices are coalesced while distinct scans and mandatory failures remain eligible")
  }
}
