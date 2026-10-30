// Passive, browser-neutral PDF candidate detection. No browser APIs, content
// access, scanner verdicts, opening decisions or network requests.
const ALLOWED_FIELDS = new Set(["url", "mimeType", "filename"]);
const PDF_MIME_TYPES = new Set(["application/pdf", "application/x-pdf"]);
const GENERIC_MIME_TYPES = new Set(["application/octet-stream", "binary/octet-stream"]);
const MAX_URL_LENGTH = 8192;
const MAX_FILENAME_LENGTH = 512;

const none = Object.freeze({
  isPdfCandidate: false, evidence: "none", authorizesOpen: false
});
const unsupportedBlobUrl = Object.freeze({
  isPdfCandidate: false, evidence: "unsupported-blob-url", authorizesOpen: false
});

function candidate(evidence) {
  return Object.freeze({
    isPdfCandidate: true, evidence, authorizesOpen: false
  });
}

function safeMetadata(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return null;
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) return null;
  const fields = Object.create(null);
  for (const key of Reflect.ownKeys(value)) {
    if (typeof key !== "string" || !ALLOWED_FIELDS.has(key)) return null;
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor)) return null;
    if (descriptor.value !== undefined &&
        (typeof descriptor.value !== "string" || descriptor.value.length > MAX_URL_LENGTH)) {
      return null;
    }
    fields[key] = descriptor.value;
  }
  return fields;
}

function pdfFilename(value) {
  return typeof value === "string" && value.length <= MAX_FILENAME_LENGTH &&
    !/[\\/\u0000-\u001f\u007f]/.test(value) &&
    /^[^\.].*\.pdf$/i.test(value);
}

function pdfUrlPath(rawUrl) {
  if (typeof rawUrl !== "string" || rawUrl.length > MAX_URL_LENGTH) return false;
  try {
    const url = new URL(rawUrl);
    // No detection of data:, javascript:, blob:, ftp: or extension URLs.
    // This function does not fetch or access file: URLs, regardless of matching.
    if (!["http:", "https:", "file:"].includes(url.protocol)) return false;
    const lastSegment = url.pathname.split("/").at(-1);
    return pdfFilename(decodeURIComponent(lastSegment));
  } catch {
    return false;
  }
}

function isBlobUrl(rawUrl) {
  if (typeof rawUrl !== "string" || rawUrl.length > MAX_URL_LENGTH) return false;
  try {
    // This inspects only the scheme: the nested origin/path of an opaque
    // object URL cannot establish PDF bytes or provide a fetchable file.
    return new URL(rawUrl).protocol === "blob:";
  } catch {
    return /^blob:/i.test(rawUrl);
  }
}

/**
 * Check browser-provided metadata only. A candidate is NOT a verified PDF,
 * proof of safe content or permission to open, scan, download or route it.
 * Blob URLs are explicitly unsupported even alongside PDF MIME/filename hints:
 * those hints cannot make an opaque object URL an accessible, scanned PDF.
 *
 * @param {{url?: string, mimeType?: string, filename?: string}} metadata
 * @returns {{isPdfCandidate: boolean, evidence: string, authorizesOpen: false}}
 */
export function detectPdfCandidate(metadata) {
  const fields = safeMetadata(metadata);
  if (!fields) return none;

  // Apply this before all hints, including MIME and filename, so callers can
  // distinguish unsupported browser-owned blob URLs from ordinary non-PDFs.
  if (isBlobUrl(fields.url)) return unsupportedBlobUrl;

  const mime = fields.mimeType === undefined ? "" :
    fields.mimeType.split(";", 1)[0].trim().toLowerCase();
  if (PDF_MIME_TYPES.has(mime)) return candidate("mime-type");
  // A known non-PDF content type must not be overridden by a misleading URL.
  if (mime && !GENERIC_MIME_TYPES.has(mime)) return none;
  if (pdfFilename(fields.filename)) return candidate("filename");
  if (pdfUrlPath(fields.url)) return candidate("url-path");
  return none;
}
