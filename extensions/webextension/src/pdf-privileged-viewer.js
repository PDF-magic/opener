// Passive identification of known browser-owned PDF viewer document URLs.
// A viewer shell is not proof that a PDF was loaded, inspected or scanned.
const NONE = Object.freeze({
  isPrivilegedPdfViewer: false, isPdfCandidate: false,
  evidence: "none", authorizesOpen: false
});
const VIEWER = Object.freeze({
  isPrivilegedPdfViewer: true, isPdfCandidate: false,
  evidence: "privileged-viewer-page", authorizesOpen: false
});
const MAX_URL_LENGTH = 8192;

function ownData(record, key) {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  return descriptor && Object.hasOwn(descriptor, "value") ?
    descriptor.value : undefined;
}

function isKnownViewer(rawUrl) {
  if (typeof rawUrl !== "string" || rawUrl.length > MAX_URL_LENGTH) return false;
  const url = new URL(rawUrl);
  if (url.username || url.password || url.port) return false;

  // Chromium's built-in, browser-controlled PDF component, not an arbitrary
  // extension or any other chrome-extension:// URL.
  if (url.protocol === "chrome-extension:") {
    return url.hostname === "mhjfbmdgcfjbbpaeojofohoefgiehjai" &&
      url.pathname === "/index.html";
  }

  // Firefox PDF.js bundled viewer resource. moz-extension:// UUID pages and
  // unrelated resource:// or chrome:// pages are not sufficient evidence.
  return url.protocol === "resource:" && url.hostname === "pdf.js" &&
    url.pathname === "/web/viewer.html";
}

/**
 * Recognize only known browser-owned PDF viewer *shells* from trusted browser
 * navigation metadata. This never verifies a PDF's contents or grants access
 * to restricted pages. Works for top-level and embedded viewer frames.
 *
 * @param {{tabId: number, frameId: number, url: string}} details
 * @returns {{isPrivilegedPdfViewer: boolean, isPdfCandidate: false,
 *   evidence: string, authorizesOpen: false}}
 */
export function detectPrivilegedPdfViewer(details) {
  try {
    if (details === null || typeof details !== "object" ||
        Array.isArray(details) ||
        ![Object.prototype, null].includes(Object.getPrototypeOf(details))) {
      return NONE;
    }
    const tabId = ownData(details, "tabId");
    const frameId = ownData(details, "frameId");
    if (!Number.isSafeInteger(tabId) || tabId < 0 ||
        !Number.isSafeInteger(frameId) || frameId < 0) return NONE;

    return isKnownViewer(ownData(details, "url")) ? VIEWER : NONE;
  } catch {
    // Malformed or hostile metadata must not execute getters or disclose URLs.
    return NONE;
  }
}
