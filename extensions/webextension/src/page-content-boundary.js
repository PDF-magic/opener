// Privacy boundary for metadata-only PDF scan candidate classification.
// No page DOM, HTML, text, browsing URL or downloaded bytes are collected.
// This is inert until a separately authorized integration explicitly calls it.
import { detectPdfCandidate } from "./pdf-detection.js";

const allowedFields = new Set(["kind", "id", "mime", "filename", "state", "danger", "error"]);
const none = Object.freeze({
  isPdfCandidate: false, evidence: "none", authorizesOpen: false
});

function safeDownloadMetadata(input) {
  if (input === null || typeof input !== "object" || Array.isArray(input)) return null;
  try {
    const prototype = Object.getPrototypeOf(input);
    if (prototype !== Object.prototype && prototype !== null) return null;
    const keys = Reflect.ownKeys(input);
    if (keys.length > allowedFields.size) return null;
    const fields = Object.create(null);
    for (const key of keys) {
      // A raw browser event, arbitrary page record or DOM object must not be
      // forwarded; only normalized download metadata can cross this boundary.
      if (typeof key !== "string" || !allowedFields.has(key)) return null;
      const descriptor = Object.getOwnPropertyDescriptor(input, key);
      if (!descriptor || !Object.hasOwn(descriptor, "value")) return null;
      const value = descriptor.value;
      if (key === "kind" || key === "mime" || key === "filename" ||
          key === "state" || key === "danger" || key === "error") {
        if (typeof value !== "string" || value.length > 4096 ||
            value.includes("\0")) return null;
      }
      fields[key] = value;
    }
    if (!Object.hasOwn(fields, "kind") || !Object.hasOwn(fields, "id") ||
        !["created", "changed"].includes(fields.kind) ||
        !Number.isSafeInteger(fields.id) || fields.id < 0) return null;
    return fields;
  } catch {
    // Hostile proxies and malformed metadata fail closed.
    return null;
  }
}

/**
 * Accept ONLY a normalized downloads event from the already-consented
 * browser downloads adapter. Even for PDF candidates, emit only a status:
 * never return, store or send page content, browsing URLs, local paths,
 * filenames, download identifiers, or document bytes.
 *
 * Non-PDF records, erased events, raw browser payloads and page-derived
 * objects return the inert non-candidate status. Calling this pure function
 * does not grant permissions, start a scan, or authorize opening a PDF.
 */
export function classifyPdfDownloadMetadata(event) {
  const fields = safeDownloadMetadata(event);
  if (!fields) return none;

  // The download adapter can supply an absolute local filename. Inspect
  // only its final component; never retain or return the full path.
  const filename = fields.filename;
  const basename = typeof filename === "string"
    ? filename.replaceAll("\\", "/").split("/").at(-1)
    : undefined;
  return detectPdfCandidate({ mimeType: fields.mime, filename: basename });
}
