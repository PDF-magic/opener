import AppKit
import Darwin

// Shared native scan-progress presentation for the PDF opener and any later
// native entry point. This component never starts scans or changes scan policy.
// Render bundled reading artwork locally, with orbiting magic sparkles.
final class TwilightReadingView: NSView {
    private var timer: Timer?
    private let started = Date()
    private let artwork: NSImage? = {
        let source = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let url = Bundle.main.url(forResource: "twilight-reading", withExtension: "png")
            ?? source.appendingPathComponent("twilight-reading.png")
        return NSImage(contentsOf: url)
    }()

    override func viewDidMoveToWindow() {
        timer?.invalidate()
        if window != nil {
            timer = Timer.scheduledTimer(withTimeInterval: 1.0 / 24, repeats: true) { [weak self] _ in
                self?.needsDisplay = true
            }
        }
    }

    deinit { timer?.invalidate() }

    override func draw(_ dirtyRect: NSRect) {
        let phase = Date().timeIntervalSince(started)
        let bob = sin(phase * 2) * 2
        let pink = NSColor(calibratedRed: 0.94, green: 0.25, blue: 0.64, alpha: 1)
        func line(_ points: [NSPoint], _ color: NSColor, _ width: CGFloat = 2) {
            let path = NSBezierPath()
            path.move(to: points[0])
            for point in points.dropFirst() { path.line(to: point) }
            color.setStroke(); path.lineWidth = width; path.lineCapStyle = .round; path.stroke()
        }
        if let artwork = artwork, artwork.size.width > 0, artwork.size.height > 0 {
            let scale = min(280 / artwork.size.width, 145 / artwork.size.height)
            let size = NSSize(width: artwork.size.width * scale, height: artwork.size.height * scale)
            artwork.draw(in: NSRect(x: (bounds.width - size.width) / 2,
                                    y: 109 - size.height / 2 + bob,
                                    width: size.width, height: size.height))
        }
        for index in 0..<7 {
            let angle = phase * 0.8 + Double(index) * .pi * 2 / 7
            let x = 151 + cos(angle) * 105
            let y = 109 + sin(angle) * 72
            let size = 3 + sin(phase * 3 + Double(index)) * 1.5
            line([NSPoint(x: x - size, y: y), NSPoint(x: x + size, y: y)], pink, 1.5)
            line([NSPoint(x: x, y: y - size), NSPoint(x: x, y: y + size)], pink, 1.5)
        }
    }
}

// These stages describe the native owner's observable process lifecycle, not
// ClamAV internals or a prediction that a document will be approved.
enum ScanProgressStage {
    case queued
    case starting
    case scanning

    var label: String {
        switch self {
        case .queued: return "Waiting to scan…"
        case .starting: return "Starting safety checks…"
        case .scanning: return "Scanning and verifying document…"
        }
    }
}

// The installed scan gate has one built-in, mandatory protection policy.
// This is a display descriptor, NOT a selectable or health-verified profile:
// a missing or failed scanner still blocks opening via the existing scan gate.
private enum BuiltInProtectionProfile {
    static let name = "Built-in"
    static let details = "ClamAV malware scanning · fail-closed"
}

// Read-only presentation of the installed scanner's selected PDF destination.
// Mirror the verified chooser's target-app.txt contract; never use this label
// to select a launcher, authorize opening, or change the scanner's fail-closed gate.
enum SelectedDestinationBrowser {
    private static let names = [
        "com.brave.Browser": "Brave",
        "com.google.Chrome": "Google Chrome",
        "org.chromium.Chromium": "Chromium",
        "com.microsoft.edgemac": "Microsoft Edge",
        "com.vivaldi.Vivaldi": "Vivaldi",
        "com.operasoftware.Opera": "Opera",
        "company.thebrowser.Browser": "Arc",
        "org.mozilla.firefox": "Firefox",
        "com.apple.Safari": "Safari",
    ]

    static func displayName(
        in directory: URL = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Studio/allow-and-open",
                                    isDirectory: true)
    ) -> String {
        guard directory.isFileURL else { return "Unavailable" }
        let parent = open(directory.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard parent >= 0 else { return errno == ENOENT ? "Brave" : "Unavailable" }
        defer { close(parent) }

        let file = openat(parent, "target-app.txt", O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
        guard file >= 0 else { return errno == ENOENT ? "Brave" : "Unavailable" }
        defer { close(file) }

        var info = stat()
        guard fstat(file, &info) == 0,
              (info.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG) else {
            return "Unavailable"
        }
        var bytes = [UInt8](repeating: 0, count: 257)
        let count = read(file, &bytes, bytes.count)
        guard count > 0, count <= 256,
              let text = String(bytes: bytes.prefix(count), encoding: .ascii) else {
            return "Unavailable"
        }
        let identifier = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if identifier == "system-default-browser" { return "System default browser" }
        guard identifier.count <= 255,
              identifier.range(of: "^[A-Za-z0-9][A-Za-z0-9.-]{1,254}$",
                               options: .regularExpression) != nil,
              identifier.contains("."), !identifier.contains(".."),
              identifier != "local.studio.brave-pdf-opener" else {
            return "Unavailable"
        }
        return names[identifier] ?? "Custom application (\(identifier))"
    }
}

// Future Enhanced producers may hand the panel a v2 explainable findings
// snapshot. This adapter never authorizes a PDF, trusts no document-provided
// strings, and accepts only the fixed stage/code/outcome vocabulary.
struct EnhancedFindingsProgressSnapshot {
    let summary: String
    let details: String

    private static let stages = [
        "pdfStructure": "PDF structure",
        "objectRelationships": "Object relationships",
        "embeddedFiles": "Embedded files",
        "automaticActions": "Automatic actions",
        "javascriptActions": "JavaScript actions",
        "formActions": "Form actions",
        "annotations": "Annotations",
        "incrementalRevisions": "Incremental revisions",
        "embeddedUrls": "Embedded URLs",
        "malformedStructures": "Malformed structures",
        "ambiguousStructures": "Ambiguous structures",
        "executableContent": "Executable content",
    ]
    private static let codes = [
        "malformedStructure": "Malformed structure",
        "conflictingStructure": "Conflicting structure",
        "unresolvedReference": "Unresolved reference",
        "knownMaliciousContent": "Known malicious content",
        "activeContent": "Active content",
        "suspiciousUrl": "Suspicious URL",
        "unexpectedEmbeddedFile": "Unexpected embedded file",
        "incrementalRevision": "Incremental revision",
        "unsupportedFeature": "Unsupported feature",
        "resourceLimit": "Resource limit",
        "inspectionFailure": "Inspection failure",
    ]
    private static let severities = [
        "informational": "Informational",
        "reviewRequired": "Review required",
        "suspicious": "Suspicious",
        "critical": "Critical",
        "blocking": "Blocking",
    ]
    private static let actions = [
        "recorded": ("continueRequiredChecks", "Recorded; other checks required"),
        "reviewRequired": ("requestReviewBeforeOpening", "Review required"),
        "blocking": ("stopOpening", "Opening stopped"),
        "inspectionIncomplete": ("rerunOrRepairInspection", "Inspection incomplete"),
    ]
    private static let malwareAssessments = [
        "notConfirmed": "Malware not confirmed",
    ]
    private static let maxDisplayedRows = 64

    static func decode(_ data: Data) -> EnhancedFindingsProgressSnapshot? {
        guard data.count <= 256 * 1024,
              let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              payload["schemaVersion"] as? Int == 2,
              payload["authorizesOpen"] as? Bool == false,
              let requiresBlock = payload["requiresBlock"] as? Bool,
              let stages = payload["stageResults"] as? [[String: Any]],
              !stages.isEmpty, stages.count <= 32 else {
            return nil
        }
        var seen = Set<String>()
        var rows = [String]()
        var findings = 0
        var incomplete = 0
        var calculatedBlock = false

        // Validate ALL entries even when only the first few fit the view.
        for stage in stages {
            guard let identifier = stage["stage"] as? String,
                  let stageName = Self.stages[identifier],
                  seen.insert(identifier).inserted,
                  let outcome = stage["outcome"] as? String,
                  ["completed", "incomplete", "notRun"].contains(outcome),
                  let entries = stage["findings"] as? [[String: Any]],
                  entries.count <= 128,
                  outcome != "notRun" || entries.isEmpty else {
                return nil
            }
            if outcome != "completed" {
                incomplete += 1
                calculatedBlock = true
                if rows.count < maxDisplayedRows {
                    rows.append("\(stageName): inspection \(outcome == "notRun" ? "not run" : "incomplete")")
                }
            }
            for finding in entries {
                guard let code = finding["code"] as? String,
                      let codeName = Self.codes[code],
                      let severity = finding["severity"] as? String,
                      let severityName = Self.severities[severity],
                      let result = finding["result"] as? [String: Any],
                      let resultID = result["outcome"] as? String,
                      let nextAction = result["nextAction"] as? String,
                      let (expectedAction, resultLabel) = Self.actions[resultID] else {
                    return nil
                }
                // Confirmed malicious content, blocking/critical severity, and
                // incomplete inspections cannot be downgraded by a producer.
                let expectedResult: String
                if code == "knownMaliciousContent" {
                    expectedResult = "blocking"
                } else if code == "resourceLimit" || code == "inspectionFailure" {
                    expectedResult = "inspectionIncomplete"
                } else if severity == "critical" || severity == "blocking" {
                    expectedResult = "blocking"
                } else if severity == "reviewRequired" || severity == "suspicious" {
                    expectedResult = "reviewRequired"
                } else {
                    expectedResult = "recorded"
                }
                guard resultID == expectedResult, nextAction == expectedAction else {
                    return nil
                }
                findings += 1
                if resultID != "recorded" {
                    calculatedBlock = true
                }
                // Enhanced findings are heuristic/structural evidence, never a
                // scanner-confirmed malware verdict. Legacy v2 reports default
                // to unconfirmed; unknown future values fail closed.
                let malwareAssessmentLabel: String
                if let rawAssessment = result["malwareAssessment"] {
                    guard let value = rawAssessment as? String,
                          let label = Self.malwareAssessments[value] else {
                        return nil
                    }
                    malwareAssessmentLabel = label
                } else {
                    // Older schema-v2 reports predate this additive field.
                    malwareAssessmentLabel = "Malware not confirmed"
                }
                if rows.count < maxDisplayedRows {
                    rows.append("\(stageName) · \(severityName) · \(codeName) — \(resultLabel) · \(malwareAssessmentLabel)")
                }
            }
        }
        guard calculatedBlock == requiresBlock else { return nil }
        let summary = "Enhanced findings: \(findings) · incomplete stages: \(incomplete)"
        if findings == 0 && incomplete == 0 {
            rows.append("No findings reported for these stages. This is not a clean verdict.")
        }
        if rows.count < maxDisplayedRows && (findings > 0 || incomplete > 0) {
            rows.insert("Inspection evidence only; opening is never authorized here.", at: 0)
        }
        let undisplayed = findings + incomplete - min(findings + incomplete, maxDisplayedRows)
        if undisplayed > 0 {
            rows.append("\(undisplayed) additional results not displayed; review the full report.")
        }
        return EnhancedFindingsProgressSnapshot(
            summary: summary,
            details: rows.joined(separator: "\n")
        )
    }
}

final class ScanProgressPanel: NSPanel {
    let filenameLabel = NSTextField(labelWithString: "")
    let destinationBrowserLabel = NSTextField(labelWithString: "Destination browser: Unavailable")
    let activeScansLabel = NSTextField(labelWithString: "Active scans: 0")
    let queuedDocumentCountLabel = NSTextField(labelWithString: "0 documents queued")
    let protectionProfileLabel = NSTextField(
        labelWithString: "Active protection profile: " + BuiltInProtectionProfile.name)
    let protectionProfileDetailsLabel = NSTextField(
        labelWithString: BuiltInProtectionProfile.details)
    let stageLabel = NSTextField(labelWithString: ScanProgressStage.queued.label)
    let progressIndicator = NSProgressIndicator(frame: NSRect(x: 30, y: 51, width: 300, height: 5))
    let cancelButton: NSButton
    // Hidden for the deployed Built-in scanner: Enhanced is not selectable.
    // These views display only validated, fixed-vocabulary inspection metadata.
    let enhancedFindingsLabel = NSTextField(labelWithString: "")
    let enhancedFindingsDetailsButton = NSButton(
        title: "Show technical details", target: nil, action: nil)
    let enhancedFindingsScrollView = NSScrollView(
        frame: NSRect(x: 20, y: 435, width: 320, height: 139))
    let enhancedFindingsTextView = NSTextView(frame: NSRect(x: 0, y: 0, width: 314, height: 139))
    private var enhancedFindingsDetailsExpanded = false
    private static let originalHeight: CGFloat = 458
    private static let collapsedFindingsHeight: CGFloat = 500
    private static let findingsHeight: CGFloat = 650

    init(cancelTarget: AnyObject, cancelAction: Selector) {
        cancelButton = NSButton(title: "Cancel", target: cancelTarget, action: cancelAction)
        super.init(contentRect: NSRect(x: 0, y: 0, width: 360, height: 458),
                   styleMask: [.titled], backing: .buffered, defer: false)
        enhancedFindingsDetailsButton.target = self
        enhancedFindingsDetailsButton.action = #selector(toggleEnhancedFindingsDetails(_:))
        title = "PDF Magic Opener — Scanning"
        level = .floating
        hidesOnDeactivate = false
        collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        isReleasedWhenClosed = false
        contentView?.addSubview(TwilightReadingView(
            frame: NSRect(x: 30, y: 238, width: 300, height: 205)))
        stageLabel.font = .systemFont(ofSize: 15, weight: .semibold)
        stageLabel.alignment = .center
        stageLabel.frame = NSRect(x: 20, y: 213, width: 320, height: 22)
        stageLabel.setAccessibilityLabel("Current scanning stage")
        contentView?.addSubview(stageLabel)
        filenameLabel.alignment = .center
        filenameLabel.lineBreakMode = .byTruncatingMiddle
        filenameLabel.textColor = .secondaryLabelColor
        filenameLabel.frame = NSRect(x: 20, y: 187, width: 320, height: 20)
        contentView?.addSubview(filenameLabel)
        activeScansLabel.alignment = .center
        activeScansLabel.font = .systemFont(ofSize: 12, weight: .semibold)
        activeScansLabel.textColor = .secondaryLabelColor
        activeScansLabel.frame = NSRect(x: 20, y: 161, width: 320, height: 20)
        activeScansLabel.setAccessibilityIdentifier("activeScanCount")
        activeScansLabel.setAccessibilityLabel(activeScansLabel.stringValue)
        contentView?.addSubview(activeScansLabel)
        queuedDocumentCountLabel.alignment = .center
        queuedDocumentCountLabel.font = .systemFont(ofSize: 12)
        queuedDocumentCountLabel.textColor = .secondaryLabelColor
        queuedDocumentCountLabel.frame = NSRect(x: 20, y: 137, width: 320, height: 20)
        queuedDocumentCountLabel.setAccessibilityIdentifier("queuedDocumentCount")
        queuedDocumentCountLabel.setAccessibilityLabel(queuedDocumentCountLabel.stringValue)
        contentView?.addSubview(queuedDocumentCountLabel)
        protectionProfileLabel.alignment = .center
        protectionProfileLabel.font = .systemFont(ofSize: 12, weight: .medium)
        protectionProfileLabel.textColor = .secondaryLabelColor
        protectionProfileLabel.frame = NSRect(x: 20, y: 111, width: 320, height: 20)
        protectionProfileLabel.setAccessibilityLabel(protectionProfileLabel.stringValue)
        contentView?.addSubview(protectionProfileLabel)
        protectionProfileDetailsLabel.alignment = .center
        protectionProfileDetailsLabel.font = .systemFont(ofSize: 11)
        protectionProfileDetailsLabel.textColor = .secondaryLabelColor
        protectionProfileDetailsLabel.frame = NSRect(x: 20, y: 91, width: 320, height: 18)
        contentView?.addSubview(protectionProfileDetailsLabel)
        destinationBrowserLabel.alignment = .center
        destinationBrowserLabel.font = .systemFont(ofSize: 12)
        destinationBrowserLabel.lineBreakMode = .byTruncatingMiddle
        destinationBrowserLabel.textColor = .secondaryLabelColor
        destinationBrowserLabel.frame = NSRect(x: 20, y: 67, width: 320, height: 20)
        destinationBrowserLabel.setAccessibilityLabel(destinationBrowserLabel.stringValue)
        contentView?.addSubview(destinationBrowserLabel)
        progressIndicator.style = .bar
        progressIndicator.isIndeterminate = true
        progressIndicator.startAnimation(nil)
        contentView?.addSubview(progressIndicator)
        cancelButton.bezelStyle = .rounded
        cancelButton.frame = NSRect(x: 136, y: 8, width: 88, height: 28)
        contentView?.addSubview(cancelButton)
        enhancedFindingsLabel.frame = NSRect(x: 20, y: 462, width: 320, height: 22)
        enhancedFindingsLabel.font = .systemFont(ofSize: 12, weight: .semibold)
        enhancedFindingsLabel.alignment = .center
        enhancedFindingsLabel.lineBreakMode = .byTruncatingTail
        enhancedFindingsLabel.setAccessibilityIdentifier("enhancedFindingsSummary")
        enhancedFindingsLabel.isHidden = true
        contentView?.addSubview(enhancedFindingsLabel)
        enhancedFindingsDetailsButton.bezelStyle = .rounded
        enhancedFindingsDetailsButton.frame = NSRect(x: 100, y: 432, width: 160, height: 24)
        enhancedFindingsDetailsButton.setAccessibilityIdentifier("enhancedFindingsDetailsToggle")
        enhancedFindingsDetailsButton.setAccessibilityLabel("Show technical details")
        enhancedFindingsDetailsButton.setAccessibilityHelp(
            "Show optional technical details for Enhanced PDF findings.")
        enhancedFindingsDetailsButton.isHidden = true
        contentView?.addSubview(enhancedFindingsDetailsButton)
        enhancedFindingsTextView.isEditable = false
        enhancedFindingsTextView.isSelectable = true
        enhancedFindingsTextView.isRichText = false
        enhancedFindingsTextView.drawsBackground = false
        enhancedFindingsTextView.font = .systemFont(ofSize: 11)
        enhancedFindingsTextView.isVerticallyResizable = true
        enhancedFindingsTextView.isHorizontallyResizable = false
        enhancedFindingsTextView.autoresizingMask = [.width]
        enhancedFindingsTextView.textContainer?.widthTracksTextView = true
        enhancedFindingsTextView.textContainer?.containerSize = NSSize(
            width: 314, height: CGFloat.greatestFiniteMagnitude)
        enhancedFindingsTextView.setAccessibilityIdentifier("enhancedFindingsDetails")
        enhancedFindingsScrollView.documentView = enhancedFindingsTextView
        enhancedFindingsScrollView.hasVerticalScroller = true
        enhancedFindingsScrollView.drawsBackground = false
        enhancedFindingsScrollView.isHidden = true
        contentView?.addSubview(enhancedFindingsScrollView)
        center()
    }

    @objc private func toggleEnhancedFindingsDetails(_ sender: NSButton) {
        guard !enhancedFindingsLabel.isHidden else { return }
        setEnhancedFindingsDetailsExpanded(!enhancedFindingsDetailsExpanded)
    }

    // Technical evidence is opt-in for routine progress viewing. The summary
    // remains visible while the detailed, selectable report is disclosed.
    private func setEnhancedFindingsDetailsExpanded(_ expanded: Bool) {
        enhancedFindingsDetailsExpanded = expanded
        enhancedFindingsDetailsButton.title = expanded
            ? "Hide technical details" : "Show technical details"
        enhancedFindingsDetailsButton.setAccessibilityLabel(enhancedFindingsDetailsButton.title)
        enhancedFindingsDetailsButton.setAccessibilityHelp(
            expanded
                ? "Hide optional technical details for Enhanced PDF findings."
                : "Show optional technical details for Enhanced PDF findings.")
        enhancedFindingsLabel.frame = NSRect(
            x: 20, y: expanded ? 608 : 462, width: 320, height: 22)
        enhancedFindingsDetailsButton.frame = NSRect(
            x: 100, y: expanded ? 578 : 432, width: 160, height: 24)
        enhancedFindingsScrollView.frame = NSRect(x: 20, y: 435, width: 320, height: 139)
        enhancedFindingsScrollView.isHidden = !expanded
        setContentSize(NSSize(
            width: 360,
            height: expanded ? Self.findingsHeight : Self.collapsedFindingsHeight))
    }

    // Presentation only: callers must supply validated v2 analysis evidence
    // from a trusted, separate Enhanced producer. No parser/scanner policy
    // changes or automatic file opening can result from this method.
    func updateEnhancedFindings(from report: Data?) {
        guard let report else {
            enhancedFindingsLabel.stringValue = ""
            enhancedFindingsLabel.setAccessibilityLabel("")
            enhancedFindingsTextView.string = ""
            enhancedFindingsLabel.isHidden = true
            enhancedFindingsDetailsButton.isHidden = true
            setEnhancedFindingsDetailsExpanded(false)
            setContentSize(NSSize(width: 360, height: Self.originalHeight))
            return
        }
        let snapshot = EnhancedFindingsProgressSnapshot.decode(report)
        enhancedFindingsLabel.stringValue = snapshot?.summary
            ?? "Enhanced findings unavailable"
        enhancedFindingsLabel.setAccessibilityLabel(enhancedFindingsLabel.stringValue)
        enhancedFindingsTextView.string = snapshot?.details
            ?? "Inspection report could not be verified. No opening decision follows."
        enhancedFindingsLabel.isHidden = false
        enhancedFindingsDetailsButton.isHidden = false
        setEnhancedFindingsDetailsExpanded(false)
    }

    // An individual scan has no trustworthy percentage. For a batch, only
    // finished request counts are measurable: not ClamAV bytes, ETA or approval.
    // Keep this separate from the active/queued document count labels.
    func updateBatchProgress(_ batchProgress: (completed: Int, total: Int)?) {
        if let batchProgress, batchProgress.total > 1,
           batchProgress.completed >= 0,
           batchProgress.completed <= batchProgress.total {
            if progressIndicator.isIndeterminate {
                progressIndicator.stopAnimation(nil)
                progressIndicator.isIndeterminate = false
            }
            progressIndicator.minValue = 0
            progressIndicator.maxValue = Double(batchProgress.total)
            progressIndicator.doubleValue = Double(batchProgress.completed)
            let description = "\(batchProgress.completed) of \(batchProgress.total) document requests processed"
            progressIndicator.setAccessibilityLabel(description)
            progressIndicator.toolTip = description
        } else {
            if !progressIndicator.isIndeterminate {
                progressIndicator.isIndeterminate = true
                progressIndicator.startAnimation(nil)
            }
            progressIndicator.setAccessibilityLabel("Individual scan progress is unknown")
            progressIndicator.toolTip = "Individual scan progress is unknown"
        }
    }

    // This is information only: the scan gate still chooses and validates
    // the actual application after a successful verdict.
    func updateDestinationBrowser(_ displayName: String) {
        destinationBrowserLabel.stringValue = "Destination browser: \(displayName)"
        destinationBrowserLabel.setAccessibilityLabel(destinationBrowserLabel.stringValue)
    }

    // Blocked files need an explicit Close, not a scan retry or automatic exit.
    func showAttentionRequired(documentDescription: String) {
        filenameLabel.stringValue = documentDescription
        stageLabel.stringValue = "Attention required — opening stopped"
        activeScansLabel.stringValue = "Active scans: 0"
        activeScansLabel.setAccessibilityLabel(activeScansLabel.stringValue)
        queuedDocumentCountLabel.stringValue = "0 documents queued"
        queuedDocumentCountLabel.setAccessibilityLabel(queuedDocumentCountLabel.stringValue)
        progressIndicator.isHidden = true
        cancelButton.title = "Close"
        orderFrontRegardless()
    }

    // Set only display state. Callers own the scan lifecycle and Cancel action.
    func show(documentDescription: String, stage: ScanProgressStage = .queued,
              queuedDocumentCount: Int = 0, activeScans: Int = 0) {
        progressIndicator.isHidden = false
        cancelButton.title = "Cancel"
        filenameLabel.stringValue = documentDescription
        stageLabel.stringValue = stage.label
        // Count only processes confirmed launched by the native owner, never
        // queued documents, scheduled workers, or duplicate open events.
        let count = max(0, activeScans)
        activeScansLabel.stringValue = "Active scans: \(count)"
        activeScansLabel.setAccessibilityLabel(activeScansLabel.stringValue)
        // Only waiting documents are counted; active scans are displayed above.
        let waiting = max(0, queuedDocumentCount)
        let waitingText = "\(waiting) \(waiting == 1 ? "document" : "documents") queued"
        queuedDocumentCountLabel.stringValue = waitingText
        queuedDocumentCountLabel.setAccessibilityLabel(waitingText)
        orderFrontRegardless()
    }
}
