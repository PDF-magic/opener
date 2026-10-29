import SwiftUI

// The installed ClamAV gate owns the effective protection policy. These
// planned tier cards can be selected for comparison only; their persistent
// preview preference never claims an unavailable tier is enforcing scans.
// These display-only check IDs mirror protection_policy_definitions.py.
// The native view intentionally does not alter scanner policy or preferences.
private struct ProtectionLevelCheck: Identifiable {
  enum Availability: String {
    case current = "Current Built-in safeguard"
    case planned = "Planned; not active"
  }

  let id: String
  let title: String
  let explanation: String
  let availability: Availability
}

private enum ProtectionLevelCheckCatalog {
  static let clamav = ProtectionLevelCheck(
    id: "clamav_scan_gate",
    title: "ClamAV malware scan",
    explanation: "Scan locally before allowing a PDF to open.",
    availability: .current
  )
  static let signatures = ProtectionLevelCheck(
    id: "signature_freshness",
    title: "Malware signature freshness",
    explanation: "Check the installed signature database before scanning.",
    availability: .current
  )
  static let integrity = ProtectionLevelCheck(
    id: "file_integrity",
    title: "File integrity verification",
    explanation: "Reject files that change between scan and handoff.",
    availability: .current
  )
  static let handoff = ProtectionLevelCheck(
    id: "fail_closed_handoff",
    title: "Fail-closed verified opening",
    explanation: "Block unsafe, incomplete or unverified opening attempts.",
    availability: .current
  )
  static let structure = ProtectionLevelCheck(
    id: "pdf_structure_validation",
    title: "PDF structure validation",
    explanation: "Planned required Enhanced inspection of PDF structure.",
    availability: .planned
  )
  static let isolated = ProtectionLevelCheck(
    id: "isolated_behavior_analysis",
    title: "Isolated behavior analysis",
    explanation: "Planned isolated analysis before any opening decision.",
    availability: .planned
  )

  static let baseline: [ProtectionLevelCheck] = [
    clamav, signatures, integrity, handoff
  ]
}

// A bundle-only, optional measurement record. There is deliberately no
// benchmark number in the app until sufficient actual completed stage work
// has been measured. Native settings never start a scan or write preferences.
private struct ProtectionPerformanceEvidence: Decodable {
  struct Measurement: Decodable {
    let profile: String
    let sampleCount: Int
    let medianAdditionalMilliseconds: Double
    let p90AdditionalMilliseconds: Double
  }

  let schemaVersion: Int
  let scope: String
  let platform: String
  let workload: String
  let measurements: [Measurement]

  private static let resource: ProtectionPerformanceEvidence? = {
    guard let location = Bundle.main.url(
      forResource: "protection-performance", withExtension: "json"
    ), let contents = try? Data(contentsOf: location),
      contents.count <= 16_384 else {
      return nil
    }
    return try? JSONDecoder().decode(ProtectionPerformanceEvidence.self, from: contents)
  }()

  static func description(for profile: String) -> String {
    let unavailable = "No representative performance measurements yet."
    guard let report = resource,
      report.schemaVersion == 1,
      report.scope == "instrumentedAdditionalStages",
      report.measurements.count <= 3,
      report.platform.count >= 3, report.platform.count <= 90,
      report.workload.count >= 3, report.workload.count <= 100,
      report.measurements.filter({ $0.profile == profile }).count == 1,
      let evidence = report.measurements.first(where: { $0.profile == profile })
    else {
      return unavailable
    }

    let milliseconds = evidence.medianAdditionalMilliseconds
    let p90 = evidence.p90AdditionalMilliseconds
    guard evidence.sampleCount >= 5, evidence.sampleCount <= 101,
      milliseconds.isFinite, p90.isFinite,
      milliseconds > 0, milliseconds <= 3_600_000,
      p90 >= milliseconds, p90 <= 3_600_000
    else {
      return unavailable
    }

    return String(
      format: "Measured additional inspection time: approx. %.1f ms median, %.1f ms at the 90th percentile (%d samples). %@ · %@. Not a measured end-to-end opening estimate.",
      milliseconds, p90, evidence.sampleCount, report.platform, report.workload
    )
  }
}

private enum PlannedProtectionTier: String, CaseIterable, Identifiable {
  case standard
  case enhanced
  case maximum

  var id: String { rawValue }

  var title: String {
    switch self {
    case .standard: return "Standard"
    case .enhanced: return "Enhanced"
    case .maximum: return "Maximum"
    }
  }

  var summary: String {
    switch self {
    case .standard:
      return "Baseline ClamAV, signature freshness and verified handoff."
    case .enhanced:
      return "Planned additional inspection for PDF structures and active content."
    case .maximum:
      return "Planned isolated analysis and sanitized-copy protections."
    }
  }

  var detail: String {
    switch self {
    case .standard:
      return "Standard is a planned named tier. Existing Built-in scanning remains the active, mandatory policy."
    case .enhanced:
      return "Enhanced is not available for enforcement. Its additional inspection stages must be fully integrated and verified before activation."
    case .maximum:
      return "Maximum is not available for enforcement. Its isolated analysis, rasterization and safe-copy safeguards are still being integrated."
    }
  }

  // Required/optional status comes from the inactive structured policy contract.
  // Planned checks remain labeled planned even when individual analyzers exist.
  var requiredChecks: [ProtectionLevelCheck] {
    switch self {
    case .standard:
      return ProtectionLevelCheckCatalog.baseline
    case .enhanced:
      return ProtectionLevelCheckCatalog.baseline + [
        ProtectionLevelCheckCatalog.structure
      ]
    case .maximum:
      return ProtectionLevelCheckCatalog.baseline + [
        ProtectionLevelCheckCatalog.structure,
        ProtectionLevelCheckCatalog.isolated
      ]
    }
  }

  var optionalChecks: [ProtectionLevelCheck] {
    switch self {
    case .standard:
      return [ProtectionLevelCheckCatalog.structure]
    case .enhanced:
      return [ProtectionLevelCheckCatalog.isolated]
    case .maximum:
      return []
    }
  }
}

// This is the complete, currently enforced policy contract returned by
// effective_protection_policy.resolve_effective_policy(). Tests verify every
// field against that authoritative resolver. It is intentionally separate from
// user-selected previews and does not inspect or modify scanner state.
private enum ExactEffectiveScanPolicy {
  static let json = """
    {
      "profile_id": "built-in",
      "required_checks": [
        "clamav_scan_gate",
        "signature_freshness",
        "file_integrity",
        "fail_closed_handoff"
      ],
      "optional_checks": [],
      "failure_disposition": "deny"
    }
    """
}

struct ProtectionSettingsView: View {
  @State private var selectedPreview: PlannedProtectionTier?
  @State private var previewSaveStatus: String?
  @State private var showExactEffectivePolicy = false
  @State private var showProtectionResetConfirmation = false

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        Text("Protection")
          .font(.largeTitle.weight(.semibold))
          .accessibilityAddTraits(.isHeader)

        Text("How PDF Magic Opener checks files before opening them.")
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)

        Text("Active protection: Built-in ClamAV scanning and fail-closed opening.")
          .font(.headline)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("activeBuiltInProtection")

        DisclosureGroup(isExpanded: $showExactEffectivePolicy) {
          VStack(alignment: .leading, spacing: 10) {
            Text("The complete enforced policy contract for new scans, not a planned protection preview:")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)

            Text(ExactEffectiveScanPolicy.json)
              .font(.system(.footnote, design: .monospaced))
              .textSelection(.enabled)
              .fixedSize(horizontal: false, vertical: true)
              .accessibilityIdentifier("exactEffectiveScanPolicyJSON")

            Text("This policy description does not report a particular file's scan verdict, installed signature health, or request-specific runtime limits. Scanner-owned timeouts may be tightened per request. Viewing it does not change protection.")
              .font(.footnote)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(.top, 8)
        } label: {
          Text("View exact effective scan policy")
            .font(.subheadline.weight(.semibold))
        }
        .accessibilityIdentifier("viewExactEffectiveScanPolicy")
        .accessibilityHint("Expand to read the current enforced policy as JSON; this does not run a scan or change settings.")

        GroupBox("New installation recommendation") {
          VStack(alignment: .leading, spacing: 8) {
            Text("Enhanced: not yet recommended as a new-install default")
              .font(.subheadline.weight(.semibold))
              .fixedSize(horizontal: false, vertical: true)
            Text("Enhanced is a candidate for the recommended default only if testing demonstrates that its full safety checks are implemented, fail closed, and provide acceptable measured performance.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
            Text("Evidence is not sufficient yet: Enhanced is not an active selectable policy, its additional checks are not fully integrated, and no end-to-end comparison establishes a safe default. New installations retain Built-in ClamAV scanning.")
              .font(.footnote)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
        }
        .accessibilityIdentifier("enhancedNewInstallRecommendationStatus")

        GroupBox("Planned protection levels") {
          VStack(alignment: .leading, spacing: 12) {
            Text("Choose a card to preview its protections. All three are planned; choosing a card does not enable it, but immediately saves your preview choice without changing the scanner.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)

            ForEach(PlannedProtectionTier.allCases) { tier in
              Button {
                // Persist only the planned preview, never the active scanner policy.
                guard let level = PreferredProtectionLevel(rawValue: tier.rawValue),
                      PlannedProtectionLevelPreference.saveExplicitChoice(level) else {
                  previewSaveStatus = "Could not save the preview choice. The previously saved level is unchanged."
                  return
                }
                selectedPreview = tier
                previewSaveStatus = "\(tier.title) preview saved. Active protection remains Built-in."
              } label: {
                HStack(alignment: .top, spacing: 12) {
                  Image(systemName: selectedPreview == tier
                        ? "largecircle.fill.circle" : "circle")
                    .foregroundStyle(.tint)
                    .accessibilityHidden(true)

                  VStack(alignment: .leading, spacing: 6) {
                    Text(tier.title)
                      .font(.headline)
                    Text(tier.summary)
                      .foregroundStyle(.secondary)
                      .fixedSize(horizontal: false, vertical: true)
                    Text("Preview only · Not available as an active policy")
                      .font(.footnote)
                      .foregroundStyle(.secondary)
                      .fixedSize(horizontal: false, vertical: true)
                    Text(ProtectionPerformanceEvidence.description(for: tier.rawValue))
                      .font(.footnote)
                      .foregroundStyle(.secondary)
                      .fixedSize(horizontal: false, vertical: true)
                    Text("Required checks: \(tier.requiredChecks.map(\.title).joined(separator: ", "))")
                      .font(.footnote)
                      .foregroundStyle(.secondary)
                      .fixedSize(horizontal: false, vertical: true)
                    if !tier.optionalChecks.isEmpty {
                      Text("Optional planned checks: \(tier.optionalChecks.map(\.title).joined(separator: ", "))")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    }
                  }
                  Spacer(minLength: 0)
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(nsColor: .controlBackgroundColor),
                            in: RoundedRectangle(cornerRadius: 10))
                .overlay {
                  RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(
                      selectedPreview == tier
                        ? Color.accentColor : Color.secondary.opacity(0.35),
                      lineWidth: selectedPreview == tier ? 2 : 1
                    )
                }
              }
              .buttonStyle(.plain)
              .accessibilityIdentifier("protectionCard-\(tier.rawValue)")
              .accessibilityLabel("\(tier.title) protection preview")
              .accessibilityValue(selectedPreview == tier
                                  ? "Selected for preview, not active"
                                  : "Not selected, not active")
              .accessibilityHint("Show \(tier.title) details. This does not change scanning.")
            }

            if let previewSaveStatus {
              Text(previewSaveStatus)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("protectionPreviewSaveStatus")
            }

            if let selectedPreview {
              VStack(alignment: .leading, spacing: 6) {
                Text("Previewing \(selectedPreview.title)")
                  .font(.headline)
                Text(selectedPreview.detail)
                  .foregroundStyle(.secondary)
                  .fixedSize(horizontal: false, vertical: true)
                Text(ProtectionPerformanceEvidence.description(for: selectedPreview.rawValue))
                  .foregroundStyle(.secondary)
                  .fixedSize(horizontal: false, vertical: true)
                Text("Required checks")
                  .font(.subheadline.weight(.semibold))
                  .accessibilityAddTraits(.isHeader)
                ForEach(selectedPreview.requiredChecks) { check in
                  includedCheckDetail(check)
                }
                if !selectedPreview.optionalChecks.isEmpty {
                  Text("Optional planned checks")
                    .font(.subheadline.weight(.semibold))
                    .accessibilityAddTraits(.isHeader)
                  ForEach(selectedPreview.optionalChecks) { check in
                    includedCheckDetail(check)
                  }
                }
                Text("This comparison lists planned tier requirements; only the current Built-in safeguards are enforced.")
                  .font(.footnote)
                  .foregroundStyle(.secondary)
                  .fixedSize(horizontal: false, vertical: true)
              }
              .padding(12)
              .frame(maxWidth: .infinity, alignment: .leading)
              .accessibilityIdentifier("protectionCardPreviewDetail")
            }
          }
        }
        .accessibilityIdentifier("plannedProtectionCardsSection")

        GroupBox("Protection settings reset") {
          VStack(alignment: .leading, spacing: 10) {
            Text("Restore the saved planned protection preview to Standard. This does not change Built-in ClamAV protection, your chosen PDF application, scan notifications or other settings.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
            Button("Reset Protection Settings") {
              showProtectionResetConfirmation = true
            }
            .accessibilityIdentifier("resetProtectionSettingsButton")
            .accessibilityHint("Confirm before resetting only the saved planned protection preview to Standard.")
          }
          .frame(maxWidth: .infinity, alignment: .leading)
        }
        .accessibilityIdentifier("resetProtectionSettingsSection")

        GroupBox("Malware scanning") {
          protectionDetail(
            "ClamAV scanning",
            "The installed PDF handler scans documents locally before allowing them to open. A failed or incomplete scan does not approve a document.",
            helpText: "ClamAV is a local malware scanner. This description does not run a scan or verify that a specific file is safe."
          )
        }
        .accessibilityIdentifier("malwareScanningSection")

        GroupBox("Unsafe or unverified files") {
          protectionDetail(
            "Fail-closed protection",
            "Cancelled, infected, or unverified files are not handed to a destination application. The established quarantine safeguards remain in place.",
            helpText: "Fail-closed means an interrupted, unsuccessful, or inconclusive scan does not count as permission to open the file."
          )
        }
        .accessibilityIdentifier("unsafeFilesSection")

        GroupBox("Verified application handoff") {
          protectionDetail(
            "After a clean scan",
            "The installed opener verifies the selected PDF application before handoff. Viewing this page cannot change the chosen app or bypass its checks.",
            helpText: "Handoff is the step that opens a verified file in your chosen PDF app; it is different from changing macOS default application settings."
          )
        }
        .accessibilityIdentifier("verifiedHandoffSection")

        Text("This page is informational and does not change scan settings. Saved preview choices are restored after restarting Settings, while Built-in ClamAV remains active.")
          .font(.footnote)
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
      .padding(28)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .accessibilityIdentifier("protectionSettingsPage")
    .onAppear {
      if let stored = PlannedProtectionLevelPreference.selected(),
         let tier = PlannedProtectionTier(rawValue: stored.rawValue) {
        selectedPreview = tier
      }
    }
    .confirmationDialog(
      "Reset Protection Settings?",
      isPresented: $showProtectionResetConfirmation
    ) {
      Button("Reset Protection Settings", role: .destructive) {
        resetProtectionPreview()
      }
      Button("Cancel", role: .cancel) {}
    } message: {
      Text("Reset only the planned protection preview to Standard? Your active Built-in ClamAV scanner, PDF app, notifications and other preferences will not change.")
    }
  }

  private func resetProtectionPreview() {
    guard ProtectionSettingsReset.reset() else {
      previewSaveStatus = "Could not reset the protection preview. Your saved choice was preserved."
      return
    }
    // Reflect the value only after the shared preference confirms persistence.
    selectedPreview = PlannedProtectionTier(rawValue: PreferredProtectionLevel.standard.rawValue)
    previewSaveStatus = "Protection preview reset to Standard. Active protection remains Built-in."
  }

  private func includedCheckDetail(_ check: ProtectionLevelCheck) -> some View {
    VStack(alignment: .leading, spacing: 4) {
      HStack(alignment: .firstTextBaseline, spacing: 8) {
        Text(check.title)
          .font(.subheadline.weight(.medium))
        Spacer(minLength: 0)
        Text(check.availability.rawValue)
          .font(.caption)
          .foregroundStyle(.secondary)
      }
      Text(check.explanation)
        .font(.footnote)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
    }
    .padding(.vertical, 4)
    .frame(maxWidth: .infinity, alignment: .leading)
    .accessibilityElement(children: .combine)
    .accessibilityIdentifier("protectionCheck-\(check.id)")
  }

  private func protectionDetail(_ title: String, _ explanation: String, helpText: String) -> some View {
    VStack(alignment: .leading, spacing: 6) {
      Text(title)
        .font(.headline)
      Text(explanation)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
      Label(helpText, systemImage: "info.circle")
        .font(.footnote)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
        .help(helpText)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(12)
  }
}
