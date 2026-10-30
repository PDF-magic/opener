import { isValidDeclaredDownloadMime } from "./download-mime.js";
import { detectPdfCandidate } from "./pdf-detection.js";

// A MIME declaration from a trusted browser response API is only candidate
// evidence. It is never a content verdict, scanner result or opening grant.
const NONE = Object.freeze({
  isPdfCandidate: false, evidence: "none", authorizesOpen: false
});
const MAX_RESPONSE_HEADERS = 128;

function ownData(record, key) {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  return descriptor && Object.hasOwn(descriptor, "value")
    ? descriptor.value : undefined;
}

function plainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value) &&
    [Object.prototype, null].includes(Object.getPrototypeOf(value));
}

function headerMime(headers) {
  if (!Array.isArray(headers) || headers.length > MAX_RESPONSE_HEADERS) return null;
  let found = null;
  for (let i = 0; i < headers.length; i++) {
    if (!Object.hasOwn(headers, i)) return null;
    const header = ownData(headers, String(i));
    if (!plainObject(header)) return null;
    const name = ownData(header, "name");
    if (typeof name !== "string") return null;
    if (name.toLowerCase() !== "content-type") continue;
    // Conflicting or repeated declarations must never select a PDF candidate.
    if (found !== null) return null;
    const value = ownData(header, "value");
    if (!isValidDeclaredDownloadMime(value)) return null;
    found = value;
  }
  return found;
}

function mediaType(mime) {
  return mime.split(";", 1)[0].toLowerCase();
}

/**
 * Read PDF MIME evidence only from an explicitly trusted browser-provided
 * main-frame response event. Chromium/Firefox webRequest.onHeadersReceived can
 * expose responseHeaders with separately authorized response-header access;
 * some compatible APIs expose mimeType directly. Unsupported or missing
 * metadata yields a non-candidate, never a URL-based fallback.
 *
 * This helper does not register webRequest listeners, request permissions,
 * fetch URLs, inspect bytes, send native messages, scan or open anything.
 * The caller must separately verify the event source and permissions.
 */
// Expose a response media type only after all frame, value, and header
// consistency checks pass. Never use navigation URL or filename as fallback.
function trustedMainFrameMime(details) {
  if (!plainObject(details) ||
      ownData(details, "type") !== "main_frame" ||
      ownData(details, "frameId") !== 0) return null;
  const tabId = ownData(details, "tabId");
  if (!Number.isSafeInteger(tabId) || tabId < 0) return null;

  const direct = ownData(details, "mimeType");
  const headers = ownData(details, "responseHeaders");
  if (Object.hasOwn(details, "mimeType") &&
      !isValidDeclaredDownloadMime(direct)) return null;
  if (Object.hasOwn(details, "responseHeaders") &&
      !Array.isArray(headers)) return null;
  const fromHeaders = headers === undefined ? null : headerMime(headers);
  if (headers !== undefined && fromHeaders === null) return null;
  if (direct === undefined && fromHeaders === null) return null;
  if (direct !== undefined && fromHeaders !== null &&
      mediaType(direct) !== mediaType(fromHeaders)) return null;
  return direct ?? fromHeaders;
}

export function detectPdfResponseMime(details) {
  try {
    const mime = trustedMainFrameMime(details);
    if (mime === null) return NONE;
    const result = detectPdfCandidate({ mimeType: mime });
    return result.isPdfCandidate && result.evidence === "mime-type" ?
      result : NONE;
  } catch {
    // Browser object traps and malformed headers are not trusted evidence.
    return NONE;
  }
}

// A PDF-like URL or suggested filename never overrules an explicitly observed
// HTML document response. These are declarative classifications, not bytes.
const NO_PAGE = Object.freeze({
  isHtmlPage: false, isPdfCandidate: false,
  evidence: "none", authorizesOpen: false
});
const HTML_PAGE = Object.freeze({
  isHtmlPage: true, isPdfCandidate: false,
  evidence: "html-mime-type", authorizesOpen: false
});
const PDF_PAGE = Object.freeze({
  isHtmlPage: false, isPdfCandidate: true,
  evidence: "mime-type", authorizesOpen: false
});
const HTML_MIME_TYPES = new Set(["text/html", "application/xhtml+xml"]);

/**
 * Classify a trusted browser main-frame response as explicitly HTML or PDF.
 * Missing, conflicting, malformed, unrelated and ambiguous MIME evidence
 * fails closed as neither. A URL suffix, filename, HTML title, or page script
 * can never upgrade a response to a PDF. No body is fetched or inspected.
 *
 * This classifier does not authenticate the caller's browser-event source or
 * grant page privileges; the extension's installed scanner remains mandatory.
 */
export function classifyHtmlOrPdfResponse(details) {
  try {
    const mime = trustedMainFrameMime(details);
    if (mime === null) return NO_PAGE;
    const normalized = mediaType(mime);
    if (HTML_MIME_TYPES.has(normalized)) return HTML_PAGE;
    const result = detectPdfCandidate({ mimeType: mime });
    return result.isPdfCandidate && result.evidence === "mime-type" ?
      PDF_PAGE : NO_PAGE;
  } catch {
    return NO_PAGE;
  }
}
