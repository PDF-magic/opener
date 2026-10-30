import { detectPdfCandidate } from "./pdf-detection.js";
import { detectPdfNavigation } from "./pdf-navigation.js";
import { detectPdfResponseMime } from "./pdf-response-mime.js";

// Passive document-only scope gate. No browser listeners, native access or scans.
const NONE = Object.freeze({
  isPdfCandidate: false, evidence: "none",
  authorizesScan: false, authorizesOpen: false
});
const TOP_URL = Object.freeze({
  isPdfCandidate: true, evidence: "document-url",
  authorizesScan: false, authorizesOpen: false
});
const TOP_MIME = Object.freeze({
  isPdfCandidate: true, evidence: "document-response-mime",
  authorizesScan: false, authorizesOpen: false
});
const FRAME_URL = Object.freeze({
  isPdfCandidate: true, evidence: "embedded-document-url",
  authorizesScan: false, authorizesOpen: false
});

function own(record, key) {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  return descriptor && Object.hasOwn(descriptor, "value")
    ? descriptor.value : undefined;
}

/**
 * Consider trusted browser *document* events only. Scripts, images, styles,
 * fonts, XHR/fetch, plugins and other page requests are never PDF candidates,
 * even if they claim a PDF filename or MIME. This is not scan authorization.
 * Main-frame MIME validation and URL navigation reuse existing classifiers.
 * Subframes accept URL-path evidence only, not unverified response MIME.
 */
export function classifyPdfDocumentResource(details) {
  try {
    if (details === null || typeof details !== "object" ||
        Array.isArray(details) ||
        ![Object.prototype, null].includes(Object.getPrototypeOf(details))) {
      return NONE;
    }
    const type = own(details, "type");
    const tabId = own(details, "tabId");
    const frameId = own(details, "frameId");
    const rawUrl = own(details, "url");
    if (!Number.isSafeInteger(tabId) || tabId < 0 ||
        !Number.isSafeInteger(frameId) || frameId < 0 ||
        !((type === "main_frame" && frameId === 0) ||
          (type === "sub_frame" && frameId > 0)) ||
        typeof rawUrl !== "string" || !rawUrl.length ||
        rawUrl.length > 8192 || /[\u0000-\u0020\u007f]/u.test(rawUrl)) {
      return NONE;
    }
    const url = new URL(rawUrl);
    if (!["http:", "https:", "file:"].includes(url.protocol) ||
        (url.protocol !== "file:" && !url.hostname) ||
        url.username || url.password) return NONE;

    // Supplied non-PDF or malformed MIME cannot fall back to a .pdf suffix.
    // Subframe MIME is not attested by the main-frame-only validator.
    const declaredMime = Object.hasOwn(details, "mimeType") ||
      Object.hasOwn(details, "responseHeaders");
    if (type === "main_frame") {
      if (declaredMime) {
        return detectPdfResponseMime(details).isPdfCandidate ? TOP_MIME : NONE;
      }
      return detectPdfNavigation(details).isPdfCandidate ? TOP_URL : NONE;
    }
    if (declaredMime) return NONE;
    const result = detectPdfCandidate({ url: rawUrl });
    return result.isPdfCandidate && result.evidence === "url-path"
      ? FRAME_URL : NONE;
  } catch {
    // Malformed metadata and hostile proxy traps fail closed, path-free.
    return NONE;
  }
}
