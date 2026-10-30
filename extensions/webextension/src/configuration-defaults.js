// Shared WebExtensions configuration defaults (opener-0574).
// Defaults are inert policy-neutral data, not browser permissions, scanner
// verdicts, or consent to watch, scan, transmit, or open a downloaded PDF.
//
// This file deliberately performs no storage reads/writes or browser API calls.
// Later tasks must separately implement validated settings loading and apply
// explicit user choices without mutating these baseline defaults.

export const EXTENSION_CONFIG_VERSION = 1;

// Every capability that could observe a download, request native processing,
// open a file, or display an unsolicited notification defaults to disabled.
// A setting alone NEVER overrides the installed app's scanner safety gates.
export const DEFAULT_EXTENSION_CONFIG = Object.freeze({
  downloadMonitoringEnabled: false,
  automaticScanRequestsEnabled: false,
  nativeMessagingEnabled: false,
  automaticOpenEnabled: false,
  notificationsEnabled: false
});

/** Return a fresh, independent snapshot for callers that need a settings seed. */
export function createDefaultExtensionConfig() {
  return { ...DEFAULT_EXTENSION_CONFIG };
}
