import { detectPdfCandidate } from "./pdf-detection.js";

// Passive Scan This PDF link-menu descriptor. No native scan is available.
export const PDF_LINK_CONTEXT_MENU_ID = "scan-this-pdf-link";
export const PDF_LINK_CONTEXT_MENU_LABEL = "Scan This PDF";

const ACTION = Object.freeze({
  id: PDF_LINK_CONTEXT_MENU_ID,
  title: PDF_LINK_CONTEXT_MENU_LABEL,
  contexts: Object.freeze(["link"]),
  enabled: false,
  authorizesScan: false,
  authorizesOpen: false
});

function ownData(record, field) {
  const descriptor = Object.getOwnPropertyDescriptor(record, field);
  return descriptor && Object.hasOwn(descriptor, "value") ?
    descriptor.value : undefined;
}

function plainObject(value) {
  return value !== null && typeof value === "object" &&
    !Array.isArray(value) &&
    [Object.prototype, null].includes(Object.getPrototypeOf(value));
}

function linkContext(contexts) {
  if (!Array.isArray(contexts) ||
      Object.getPrototypeOf(contexts) !== Array.prototype ||
      contexts.length < 1 || contexts.length > 8) return false;
  let linked = false;
  const seen = new Set();
  for (let i = 0; i < contexts.length; i++) {
    if (!Object.hasOwn(contexts, i)) return false;
    const context = ownData(contexts, String(i));
    if (typeof context !== "string" || !context || seen.has(context)) return false;
    seen.add(context);
    if (context === "link") linked = true;
  }
  return linked;
}

function supportedLink(rawUrl) {
  if (typeof rawUrl !== "string" || rawUrl.length === 0 ||
      rawUrl.length > 8192 || /[\u0000-\u0020\u007f]/u.test(rawUrl)) return false;
  const parsed = new URL(rawUrl);
  if (!["http:", "https:"].includes(parsed.protocol) ||
      !parsed.hostname || parsed.username || parsed.password) return false;
  // URL-path evidence only: query parameters and filenames cannot qualify.
  const candidate = detectPdfCandidate({ url: rawUrl });
  return candidate.isPdfCandidate && candidate.evidence === "url-path";
}

/**
 * Given a separately authenticated browser contextMenus.onShown-like event,
 * return an immutable disabled item only for a supported HTTP(S) PDF link.
 * This does not register menu items or install any browser event listener.
 */
export function describePdfLinkContextMenu(details) {
  try {
    if (!plainObject(details) ||
        !linkContext(ownData(details, "contexts")) ||
        !supportedLink(ownData(details, "linkUrl"))) return null;
    return ACTION;
  } catch {
    // Malformed metadata, accessors, and proxy traps fail closed.
    return null;
  }
}
