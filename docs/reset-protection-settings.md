# Reset Protection Settings — opener-0340

Protection Preferences now offers a **Reset Protection Settings** button with a confirmation dialog and a cancel option. It is **not** a reset of the installed malware scanner, PDF-opening association, quarantine, signature freshness checks, caches, notification settings or General preferences. Only the saved, *planned* protection-preview metadata is affected.

After explicit confirmation, the shared \`ProtectionSettingsReset.reset()\` verifies that the installed schema is current and the effective selected scanner is still **Built-in**. It then restores \`preferredProtectionLevel = "standard"\` (the existing-installation planned-level baseline from opener-0334). A fresh installation's neutral \`unassigned\` preview marker may also become Standard **only because the user explicitly confirmed Reset**. Standard remains a *preview*, **not an executable or enabled protection tier**. The UI highlights Standard only after durable persistence succeeds, with a visible success or failure message.

Unknown future values, unsupported scanner policy metadata, invalid schema versions, malformed values or absent planned-level preferences are not silently replaced. On a persistence failure, the previous value is restored on a best-effort basis and the UI retains its previous preview. Repeated resets are idempotent. The scanner's \`selectedProtectionProfile\` remains \`built-in\`; other saved user customizations are untouched.

This reset is intentionally narrower than the existing **General Preferences Reset**. Its behavior is independent of future expansion of actual protection tiers, which must undergo separate safety review before any tier can be activated or reset as an enforcement policy.

\`test-reset-protection-settings.swift\` exercises isolated UserDefaults domains, selected previews, the first-install marker, repeated resets, persistence after reopening, unknown/future/malformed settings, incompatible schema and policy, and unchanged browser/notification preferences. \`test-reset-protection-settings.py\` asserts the visible confirmation/cancel controls and that the reset cannot bypass the installed scanner. Both tests run under the existing CI, with native SwiftUI compilation on macOS.

The implementation relies on the immediate preview-persistence UI from opener-0336 / PR #226; it is scoped to the reset action, not a duplicate save implementation.
