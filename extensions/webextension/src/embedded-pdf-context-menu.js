import { detectPdfIframe } from "./pdf-iframe.js";
import { detectPdfEmbedElement } from "./pdf-embed-element.js";

// A passive future context-menu contract, not a registered browser menu.
// A live handler requires separately reviewed browser permissions and native
// scan-before-open coordination. Never derive permission from page content.
export const EMBEDDED_PDF_MENU_ID = "scan-supported-embedded-pdf";
export const EMBEDDED_PDF_MENU_TITLE = "Scan This Embedded PDF";
export const EMBEDDED_PDF_UNAVAILABLE_MESSAGE =
  "Scan This Embedded PDF requires trusted browser context and a verified native scanner.";

const UNSUPPORTED = Object.freeze({
  menuItemId: EMBEDDED_PDF_MENU_ID, title: EMBEDDED_PDF_MENU_TITLE,
  supported: false, enabled: false, evidence: "none",
  unavailableMessage: EMBEDDED_PDF_UNAVAILABLE_MESSAGE,
  authorizesScan: false, authorizesOpen: false
});
const IFRAME = Object.freeze({
  menuItemId: EMBEDDED_PDF_MENU_ID, title: EMBEDDED_PDF_MENU_TITLE,
  supported: true, enabled: false, evidence: "iframe-src",
  unavailableMessage: EMBEDDED_PDF_UNAVAILABLE_MESSAGE,
  authorizesScan: false, authorizesOpen: false
});
const EMBED = Object.freeze({
  menuItemId: EMBEDDED_PDF_MENU_ID, title: EMBEDDED_PDF_MENU_TITLE,
  supported: true, enabled: false, evidence: "embed-element",
  unavailableMessage: EMBEDDED_PDF_UNAVAILABLE_MESSAGE,
  authorizesScan: false, authorizesOpen: false
});
const NOT_REQUESTED = Object.freeze({
  status: "not-requested", scanVerified: false, authorizesScan: false,
  authorizesOpen: false
});
const NOT_SUPPORTED = Object.freeze({
  status: "unsupported", scanVerified: false, authorizesScan: false,
  authorizesOpen: false
});
const UNAVAILABLE = Object.freeze({
  status: "unavailable", scanVerified: false, authorizesScan: false,
  authorizesOpen: false
});

function trustedSnapshot(record) {
  if (record === null || typeof record !== "object" || Array.isArray(record) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(record))) {
    return null;
  }
  const keys = Reflect.ownKeys(record);
  if (keys.length !== 4 ||
      !["source", "tabId", "frameId", "element"].every(key => keys.includes(key))) {
    return null;
  }
  const fields = Object.create(null);
  for (const key of keys) {
    if (typeof key !== "string" ||
        !["source", "tabId", "frameId", "element"].includes(key)) return null;
    const descriptor = Object.getOwnPropertyDescriptor(record, key);
    if (!descriptor || !Object.hasOwn(descriptor, "value")) return null;
    fields[key] = descriptor.value;
  }
  if (!Number.isSafeInteger(fields.tabId) || fields.tabId < 0 ||
      !Number.isSafeInteger(fields.frameId) || fields.frameId < 0) return null;
  return fields;
}

/**
 * Return a context-menu action descriptor for a *trusted* element snapshot.
 * The caller must independently authenticate the browser tab, frame and
 * original element; untrusted page data cannot prove provenance. This never
 * enumerates the DOM, registers a menu, or authorizes a scan.
 *
 * Iframe evidence requires a non-top frame and a valid PDF src. Embed evidence
 * uses only the existing strict <embed> classifier and a valid tab/frame.
 * Other elements, arbitrary page links, objects and unsupported schemes are
 * not treated as supported embedded-PDF context-menu candidates.
 */
export function embeddedPdfContextMenuState(snapshot) {
  try {
    const fields = trustedSnapshot(snapshot);
    if (!fields) return UNSUPPORTED;
    if (fields.source === "iframe" && fields.frameId > 0 &&
        detectPdfIframe(fields.element).isPdfCandidate) return IFRAME;
    if (fields.source === "embed" &&
        detectPdfEmbedElement(fields.element).isPdfCandidate) return EMBED;
  } catch {
    // Hostile objects fail closed without exposing any source URL or error.
  }
  return UNSUPPORTED;
}

/**
 * An explicit context-menu action request. Until the permissioned browser
 * adapter and verified native scanner exist, even a valid user gesture cannot
 * submit a PDF or claim a clean verdict. Do not confuse this with a live menu.
 */
export function activateEmbeddedPdfContextMenu(snapshot, userInitiated = false) {
  if (userInitiated !== true) return NOT_REQUESTED;
  return embeddedPdfContextMenuState(snapshot).supported ? UNAVAILABLE : NOT_SUPPORTED;
}
