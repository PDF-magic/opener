import AppKit
import Foundation

@main
struct BrowserPreferenceLiveRefreshTests {
    static func main() {
        func make(_ id: String, _ name: String, _ version: String? = nil) -> BrowserPreferenceItem {
            BrowserPreferenceItem(bundleIdentifier: id, name: name, version: version, icon: nil)
        }

        var installed = [make("com.brave.Browser", "Brave", "1.0")]
        var lookups = 0
        var changes = [[BrowserPreferenceItem]]()
        let refresher = BrowserPreferenceLiveRefresher(
            initialItems: installed,
            discover: {
                lookups += 1
                return installed
            },
            update: { changes.append($0) }
        )
        precondition(!refresher.refreshIfChanged(), "An unchanged inventory must not rebuild rows")
        precondition(changes.isEmpty)
        installed.append(make("com.apple.Safari", "Safari"))
        precondition(refresher.refreshIfChanged(), "New installation should refresh an open window")
        precondition(changes.last?.map(\.bundleIdentifier) == [
            "com.brave.Browser", "com.apple.Safari"
        ])
        precondition(!refresher.refreshIfChanged(), "Do not rebuild rows on every scan")
        installed.removeFirst()
        precondition(refresher.refreshIfChanged(), "Removed browser must vanish while preferences remain open")
        precondition(changes.last?.map(\.bundleIdentifier) == ["com.apple.Safari"])
        installed[0] = make("com.apple.Safari", "Safari", "26.1")
        precondition(refresher.refreshIfChanged(), "Updated metadata must refresh the row")
        precondition(changes.last?.first?.version == "26.1")
        installed.removeAll()
        precondition(refresher.refreshIfChanged(), "Removing the last browser should show empty state")
        precondition(changes.last?.isEmpty == true)
        precondition(lookups == 6 && changes.count == 4, "Each poll runs discovery; only changes update UI")

        // The timer is window-scoped. Trigger it deterministically so CI does
        // not depend on real installed apps or clock scheduling.
        installed = [make("com.google.Chrome", "Chrome")]
        refresher.start(interval: 60)
        guard let timer = refresher.timer, timer.isValid else {
            fatalError("Live refresh must create a repeating timer")
        }
        timer.fire()
        precondition(changes.last?.first?.bundleIdentifier == "com.google.Chrome",
                     "A timer tick must rediscover installed applications")
        refresher.stop()
        precondition(!timer.isValid && refresher.timer == nil,
                     "Closing preferences must stop future scans")
        print("PASS: live installation/removal refresh preserves changes only while preferences are open")
    }
}
