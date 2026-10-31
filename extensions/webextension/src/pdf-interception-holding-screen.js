// Passive, not wired into the inactive browser extension.
import { createHoldingScreenOriginalUrl } from "./holding-screen-original-url.js";
export const PDF_HOLDING_COPY = Object.freeze({
  title: "Scanning PDF before opening",
  description: "Opening is paused while PDF Magic Opener checks this PDF.",
  warning: "This PDF is not yet verified as safe. Opening remains blocked."
});
const idPattern = /^[A-Za-z0-9_-]{1,80}$/u;
const holdFields = ["navigationId", "scanRequestId", "state",
  "navigationHeld", "nativeScanStarted", "authorizesOpen"];
const unavailable = Object.freeze({ status: "unavailable", displayed: false,
  scanVerified: false, authorizesScan: false, authorizesOpen: false });
const scanning = Object.freeze({ status: "scanning", displayed: true,
  scanVerified: false, authorizesScan: false, authorizesOpen: false });

function own(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function exact(value, fields) {
  if (!value || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
  const keys = Reflect.ownKeys(value);
  return keys.length === fields.length && fields.every(key =>
    keys.includes(key) &&
    Object.hasOwn(Object.getOwnPropertyDescriptor(value, key), "value"));
}

function heldAndScanning(value, navigationId, scanRequestId) {
  return exact(value, holdFields) &&
    own(value, "navigationId") === navigationId &&
    own(value, "scanRequestId") === scanRequestId &&
    own(value, "state") === "scanning" &&
    own(value, "navigationHeld") === true &&
    own(value, "nativeScanStarted") === true &&
    own(value, "authorizesOpen") === false;
}

function validRoot(root) {
  try {
    return root?.nodeType === 1 && root.id === "pdfInterceptionHoldingScreen" &&
      typeof root.ownerDocument?.createElement === "function" &&
      typeof root.replaceChildren === "function" &&
      typeof root.setAttribute === "function" &&
      typeof root.removeAttribute === "function";
  } catch {
    return false;
  }
}

/**
 * Fixed, accessible holding UI for a future verified PDF interception gate.
 * The caller must independently authenticate the browser/navigation hold
 * and native scan. The readiness flag and the record are NOT proof.
 * No listener, permission request, scan or opening is performed here.
 */
export function createPdfInterceptionHoldingScreen(root, coordinator = null) {
  if (!validRoot(root)) {
    throw new TypeError("An extension-owned holding root is required");
  }
  let disposed = false;
  let originalUrlView = null;

  function clear() {
    originalUrlView?.dispose();
    originalUrlView = null;
    root.hidden = true;
    root.replaceChildren();
    for (const attribute of ["role", "aria-live", "aria-busy", "aria-labelledby"]) {
      root.removeAttribute(attribute);
    }
  }

  function show(context) {
    try {
      clear();
      if (disposed || !exact(context, ["navigationId", "scanRequestId"])) {
        return unavailable;
      }
      const navigationId = own(context, "navigationId");
      const scanRequestId = own(context, "scanRequestId");
      const read = own(coordinator, "readVerifiedHeldPdfScan");
      if (typeof navigationId !== "string" || !idPattern.test(navigationId) ||
          typeof scanRequestId !== "string" || !idPattern.test(scanRequestId) ||
          own(coordinator, "verifiedPdfInterceptionReady") !== true ||
          typeof read !== "function") return unavailable;
      // A synchronous independently verified snapshot avoids stale async UI.
      const hold = read.call(coordinator,
        Object.freeze({ navigationId, scanRequestId }));
      if (!heldAndScanning(hold, navigationId, scanRequestId) ||
          own(coordinator, "verifiedPdfInterceptionReady") !== true ||
          own(coordinator, "readVerifiedHeldPdfScan") !== read) return unavailable;

      const document = root.ownerDocument;
      const panel = document.createElement("div");
      panel.className = "pdf-interception-holding__panel";
      const indicator = document.createElement("span");
      indicator.className = "pdf-interception-holding__indicator";
      indicator.setAttribute("aria-hidden", "true");
      const heading = document.createElement("h1");
      heading.id = "pdf-interception-holding-title";
      heading.textContent = PDF_HOLDING_COPY.title;
      const description = document.createElement("p");
      description.textContent = PDF_HOLDING_COPY.description;
      const urlLabel = document.createElement("p");
      urlLabel.id = "pdf-interception-holding-original-url-label";
      urlLabel.textContent = "Original PDF URL";
      const urlText = document.createElement("p");
      urlText.id = "holdingScreenOriginalUrl";
      urlText.setAttribute("aria-labelledby", urlLabel.id);
      const warning = document.createElement("p");
      warning.className = "pdf-interception-holding__warning";
      warning.textContent = PDF_HOLDING_COPY.warning;
      panel.replaceChildren(indicator, heading, description, urlLabel, urlText, warning);
      root.replaceChildren(panel);
      root.setAttribute("role", "status");
      root.setAttribute("aria-live", "polite");
      root.setAttribute("aria-busy", "true");
      root.setAttribute("aria-labelledby", heading.id);
      originalUrlView = createHoldingScreenOriginalUrl(urlText, coordinator);
      root.hidden = false;
      // The presenter independently verifies original-URL provenance,
      // and cancellation disposes it before another hold can be displayed.
      void originalUrlView.show(navigationId);
      return scanning;
    } catch {
      // Never expose raw native errors, browser URLs or PDF paths.
      try { clear(); } catch { /* best-effort neutralization */ }
      return unavailable;
    }
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    clear();
  }

  clear();
  return Object.freeze({ show, clear, dispose });
}
