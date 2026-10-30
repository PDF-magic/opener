import { detectPdfResponseMime } from "./pdf-response-mime.js";

// Browser-provided response headers are untrusted classification evidence,
// never proof of document bytes or permission to scan or open a PDF.
const NONE = Object.freeze({
  isInlineResponse: false, isPdfCandidate: false,
  evidence: "none", authorizesOpen: false
});
const INLINE = Object.freeze({
  isInlineResponse: true, isPdfCandidate: false,
  evidence: "content-disposition", authorizesOpen: false
});
const INLINE_PDF = Object.freeze({
  isInlineResponse: true, isPdfCandidate: true,
  evidence: "content-disposition+mime-type", authorizesOpen: false
});
const MAX_HEADERS = 128;
const MAX_DISPOSITION_LENGTH = 1024;
const MAX_PARAMETERS = 16;
const TOKEN = /^[A-Za-z0-9!#$%&'*+.^_|~-]+/;

function plainObject(value) {
  return value !== null && typeof value === "object" &&
    !Array.isArray(value) &&
    [Object.prototype, null].includes(Object.getPrototypeOf(value));
}

function data(record, key) {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  return descriptor && Object.hasOwn(descriptor, "value")
    ? descriptor.value : undefined;
}

// Recognize an HTTP inline disposition, not an inline-looking prefix.
// Parse parameters without reading or returning page-controlled filenames.
function isInlineDisposition(value) {
  if (typeof value !== "string" || !value.length ||
      value.length > MAX_DISPOSITION_LENGTH ||
      !/^[\x20-\x7e]+$/.test(value)) return false;

  let offset = 0;
  const spaces = () => {
    while (value[offset] === " ") offset++;
  };
  spaces();
  if (value.slice(offset, offset + 6).toLowerCase() !== "inline") return false;
  offset += 6;
  spaces();
  const names = new Set();
  while (offset < value.length) {
    if (value[offset++] !== ";" || names.size >= MAX_PARAMETERS) return false;
    spaces();
    const key = TOKEN.exec(value.slice(offset))?.[0];
    if (!key || names.has(key.toLowerCase())) return false;
    names.add(key.toLowerCase());
    offset += key.length;
    spaces();
    if (value[offset++] !== "=") return false;
    spaces();

    if (value[offset] === '"') {
      offset++;
      let closed = false;
      while (offset < value.length) {
        if (value[offset] === "\\") {
          // An escaped quote or backslash stays inside the quoted value.
          if (++offset === value.length) return false;
          offset++;
        } else if (value[offset] === '"') {
          offset++;
          closed = true;
          break;
        } else {
          offset++;
        }
      }
      if (!closed) return false;
    } else {
      const token = TOKEN.exec(value.slice(offset))?.[0];
      if (!token) return false;
      offset += token.length;
    }
    spaces();
  }
  return true;
}

function headerDisposition(headers) {
  if (!Array.isArray(headers) || headers.length > MAX_HEADERS) return null;
  let found;
  for (let i = 0; i < headers.length; i++) {
    if (!Object.hasOwn(headers, i)) return null;
    const header = data(headers, String(i));
    if (!plainObject(header)) return null;
    const name = data(header, "name");
    if (typeof name !== "string") return null;
    if (name.toLowerCase() !== "content-disposition") continue;
    if (found !== undefined) return null;
    found = data(header, "value");
    if (typeof found !== "string") return null;
  }
  return found;
}

/**
 * Identify the HTTP Content-Disposition: inline response *when a trusted
 * browser response event actually exposes that field*. A valid inline header
 * can be observed without a MIME type, but PDF candidacy additionally needs
 * the existing strict, independent response MIME classifier.
 *
 * This passive helper does not authenticate an event source, request browser
 * privileges, register listeners, access response bodies, scan or open files.
 */
export function detectInlinePdfResponse(details) {
  try {
    if (!plainObject(details) ||
        data(details, "type") !== "main_frame" ||
        data(details, "frameId") !== 0) return NONE;
    const tabId = data(details, "tabId");
    if (!Number.isSafeInteger(tabId) || tabId < 0) return NONE;

    const hasDirect = Object.hasOwn(details, "contentDisposition");
    const hasHeaders = Object.hasOwn(details, "responseHeaders");
    const direct = hasDirect ? data(details, "contentDisposition") : undefined;
    const headers = hasHeaders ? data(details, "responseHeaders") : undefined;
    if (hasDirect && !isInlineDisposition(direct)) return NONE;
    if (hasHeaders && !Array.isArray(headers)) return NONE;
    const fromHeaders = hasHeaders ? headerDisposition(headers) : undefined;
    if (hasHeaders && fromHeaders === null) return NONE;
    if (fromHeaders !== undefined && !isInlineDisposition(fromHeaders)) return NONE;
    if (!hasDirect && fromHeaders === undefined) return NONE;

    const mime = detectPdfResponseMime(details);
    return mime.isPdfCandidate && mime.evidence === "mime-type" ?
      INLINE_PDF : INLINE;
  } catch {
    // Never execute accessors or expose page URLs, headers or error details.
    return NONE;
  }
}
