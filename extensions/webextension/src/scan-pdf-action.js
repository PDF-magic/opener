// An explicit, fail-closed Scan PDF action contract (opener-0578).
// This module never reads a downloaded file, sends native messages, or
// confers a scanner verdict. A later trusted integration must supply a
// coordinator that presents a user-selected local PDF to the native scanner.
export const SCAN_PDF_LABEL = "Scan PDF";
export const SCAN_PDF_UNAVAILABLE_MESSAGE =
  "Scan PDF is unavailable until a verified native scanner is connected.";

const unavailable = Object.freeze({
  status: "unavailable", scanVerified: false, authorizesOpen: false
});
const notRequested = Object.freeze({
  status: "not-requested", scanVerified: false, authorizesOpen: false
});
const submitted = Object.freeze({
  status: "request-submitted", scanVerified: false, authorizesOpen: false
});

function ownData(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  try {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    return descriptor && "value" in descriptor ? descriptor.value : undefined;
  } catch {
    return undefined;
  }
}

/**
 * Create a manual Scan PDF action. The injected coordinator belongs to a
 * separately reviewed, authenticated browser-to-native integration; its
 * readiness flag is never derived from browser download metadata or from
 * the extension's configuration defaults. No scanner is provided here.
 *
 * The future UI must call activate({ userInitiated: true }) directly from an
 * explicit button click. Passing this boolean is not proof of a user gesture:
 * callers must supply their own trusted UI binding.
 */
export function createScanPdfAction(coordinator = null) {
  function available() {
    return ownData(coordinator, "manualScanReady") === true &&
      typeof ownData(coordinator, "requestUserSelectedPdfScan") === "function";
  }

  function state() {
    return Object.freeze({
      label: SCAN_PDF_LABEL,
      enabled: available(),
      unavailableMessage: SCAN_PDF_UNAVAILABLE_MESSAGE,
      scanVerified: false,
      authorizesOpen: false
    });
  }

  async function activate({ userInitiated = false } = {}) {
    if (userInitiated !== true) return notRequested;
    if (!available()) return unavailable;

    try {
      // Deliberately pass NO browser URL, path, file bytes, metadata or
      // claimed clean result. The coordinator must obtain and verify its
      // own user-selected local PDF, perform scanning and enforce policy.
      const response = await ownData(coordinator, "requestUserSelectedPdfScan").call(coordinator);
      return ownData(response, "accepted") === true ? submitted : unavailable;
    } catch {
      // Never expose source paths, scanner internals or native error details.
      return unavailable;
    }
  }

  return Object.freeze({ state, activate });
}
