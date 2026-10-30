import { detectPdfCandidate } from "./pdf-detection.js";

// PDF.js's conventional viewer route is a useful, but unverified, hint that
// a website's JavaScript viewer is displaying a PDF referenced by ?file=.
// This passive classifier never inspects page state or fetches the document.
const NONE = Object.freeze({
  isPdfCandidate: false, evidence: "none", authorizesOpen: false
});
const PDF_JS_VIEWER_PATH = /\/(?:pdfjs|pdf\.js|pdfjs-dist)\/web\/viewer\.html$/i;
const MAX_URL_LENGTH = 8192;
const MAX_FILE_REFERENCE_LENGTH = 4096;

function ownData(record, key) {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  return descriptor && Object.hasOwn(descriptor, "value")
    ? descriptor.value : undefined;
}

/**
 * Recognize conventional PDF.js web/viewer.html URLs with a single
 * same-origin HTTP(S) PDF file reference in their `file` query parameter.
 * Input must be a separately authenticated top-frame browser navigation
 * event, not an object supplied by a webpage or content script.
 *
 * URL hints alone cannot verify PDF bytes or authorize scanning/opening.
 * No permissions, DOM access, network requests or browser listeners here.
 */
export function detectJavascriptPdfViewer(details) {
  try {
    if (details === null || typeof details !== "object" ||
        Array.isArray(details) ||
        ![Object.prototype, null].includes(Object.getPrototypeOf(details)) ||
        ownData(details, "frameId") !== 0) return NONE;

    const tabId = ownData(details, "tabId");
    const rawUrl = ownData(details, "url");
    if (!Number.isSafeInteger(tabId) || tabId < 0 ||
        typeof rawUrl !== "string" || !rawUrl.length ||
        rawUrl.length > MAX_URL_LENGTH ||
        /[\u0000-\u0020\u007f]/u.test(rawUrl)) return NONE;

    // An ordinary .pdf top-frame navigation is handled by pdf-navigation.js.
    // Restrict this hint to recognizable PDF.js viewer assets, never arbitrary
    // URLs with a "file=report.pdf" query string.
    const viewer = new URL(rawUrl);
    if (!["http:", "https:"].includes(viewer.protocol) ||
        !viewer.hostname || viewer.username || viewer.password ||
        !PDF_JS_VIEWER_PATH.test(viewer.pathname)) return NONE;

    // Never select the first of conflicting query parameters.
    const files = viewer.searchParams.getAll("file");
    if (files.length !== 1 || !files[0] ||
        files[0].length > MAX_FILE_REFERENCE_LENGTH ||
        files[0] !== files[0].trim() ||
        /[\u0000-\u001f\u007f]/u.test(files[0])) return NONE;

    // PDF.js accepts relative or absolute references. Only a same-origin
    // HTTP(S) PDF path qualifies; blob:, data:, file:, javascript:, and
    // cross-origin references cannot provide this bounded path evidence.
    const target = new URL(files[0], viewer);
    if (!["http:", "https:"].includes(target.protocol) ||
        target.origin !== viewer.origin ||
        target.username || target.password) return NONE;

    const result = detectPdfCandidate({ url: target.href });
    return result.isPdfCandidate && result.evidence === "url-path"
      ? Object.freeze({
        isPdfCandidate: true, evidence: "javascript-viewer", authorizesOpen: false
      })
      : NONE;
  } catch {
    // Malformed URLs, accessors and hostile proxy traps fail closed.
    // Never return, retain or log URL parameters or private PDF filenames.
    return NONE;
  }
}
