// An opt-in availability gate for the explicit "Scan This PDF" toolbar action.
// No browser/DOM inspection, native transport, scanning or opening occurs here.
export const SCAN_THIS_PDF_LABEL = "Scan This PDF";
export const SCAN_THIS_PDF_UNAVAILABLE_MESSAGE =
  "Scan This PDF is unavailable until a verified native scanner and trusted current-PDF selection are connected.";

const requiredEvidence = Object.freeze([
  "pdfIdentified", "currentDocumentVerified", "selectionVerified",
  "sourceAccessible", "permissionGranted"
]);

function own(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function plain(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value) &&
    [Object.prototype, null].includes(Object.getPrototypeOf(value));
}

function verifiedEligibility(evidence) {
  if (!plain(evidence)) return false;
  const keys = Reflect.ownKeys(evidence);
  return keys.length === requiredEvidence.length &&
    requiredEvidence.every(key => own(evidence, key) === true) &&
    keys.every(key => typeof key === "string" && requiredEvidence.includes(key));
}

const disabled = Object.freeze({
  label: SCAN_THIS_PDF_LABEL, enabled: false,
  unavailableMessage: SCAN_THIS_PDF_UNAVAILABLE_MESSAGE,
  scanVerified: false, authorizesOpen: false
});
const enabled = Object.freeze({
  label: SCAN_THIS_PDF_LABEL, enabled: true,
  unavailableMessage: SCAN_THIS_PDF_UNAVAILABLE_MESSAGE,
  scanVerified: false, authorizesOpen: false
});

/**
 * A future *authenticated* browser-to-native coordinator must supply all
 * current-document evidence. The browser's passive PDF candidate classifiers,
 * a page URL, or a configuration preference cannot supply these capabilities.
 * The caller must re-render on navigation, permission loss and disconnect;
 * state() also re-reads evidence on every call to avoid cached eligibility.
 * This module only controls availability, never submits a scan.
 */
export function createScanThisPdfEligibilityGate(coordinator = null) {
  function state() {
    try {
      if (own(coordinator, "currentPdfScanReady") !== true ||
          typeof own(coordinator, "readCurrentPdfEligibility") !== "function" ||
          typeof own(coordinator, "requestCurrentPdfScan") !== "function") return disabled;
      const evidence = own(coordinator, "readCurrentPdfEligibility").call(coordinator);
      return verifiedEligibility(evidence) ? enabled : disabled;
    } catch {
      return disabled;
    }
  }

  // Optional UI binding for an extension-owned button, supplied by a future
  // reviewed popup integration. It cannot register listeners or start a scan.
  function updateControl(button) {
    try {
      if (!button || button.tagName !== "BUTTON" || button.id !== "scanThisPDF" ||
          typeof button.setAttribute !== "function") return false;
      // Start disabled, including on exceptions and while rechecking state.
      button.disabled = true;
      button.setAttribute("aria-disabled", "true");
      const available = state().enabled;
      if (available) {
        button.disabled = false;
        button.setAttribute("aria-disabled", "false");
      }
      return available;
    } catch {
      try { button.disabled = true; button.setAttribute("aria-disabled", "true"); } catch {}
      return false;
    }
  }

  return Object.freeze({ state, updateControl });
}
