import { isValidDeclaredDownloadMime } from "./download-mime.js";
import { detectPdfCandidate } from "./pdf-detection.js";

// Pure classification of explicitly supplied <object> attributes. The caller
// must separately obtain any permission needed to observe a page's elements.
const NONE = Object.freeze({
  isPdfCandidate: false, evidence: "none", authorizesOpen: false
});
const MAX_DATA_LENGTH = 8192;
const ALLOWED_FIELDS = new Set(["tagName", "data", "type"]);

function ownData(record, key) {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function normalizedObjectData(raw) {
  if (typeof raw !== "string" || !raw.length || raw.length > MAX_DATA_LENGTH ||
      raw.trim() !== raw || /[\\\u0000-\u001f\u007f]/u.test(raw) ||
      /%(?![0-9a-f]{2})/iu.test(raw) || /^[?#]/u.test(raw)) return null;
  try {
    // Resolve relative HTML data attributes for classification only, without
    // using the page URL, reading document contents or fetching the resource.
    const url = new URL(raw, "https://pdf-object.invalid/");
    if (!["http:", "https:", "file:"].includes(url.protocol) ||
        url.username || url.password) return null;
    const tail = decodeURIComponent(url.pathname.split("/").at(-1));
    if (/[\\/\u0000-\u001f\u007f]/u.test(tail)) return null;
    return url.href;
  } catch {
    return null;
  }
}

/**
 * Classify only normalized HTML <object> metadata supplied by a trusted
 * caller, not raw DOM nodes, page HTML or browser events. A match is merely
 * an unverified PDF candidate, never authorization to scan or open a file.
 *
 * @param {{tagName: string, data: string, type?: string}} attributes
 * @returns {{isPdfCandidate: boolean, evidence: string, authorizesOpen: false}}
 */
export function detectPdfObjectEmbed(attributes) {
  try {
    if (attributes === null || typeof attributes !== "object" ||
        Array.isArray(attributes) ||
        ![Object.prototype, null].includes(Object.getPrototypeOf(attributes))) return NONE;
    const keys = Reflect.ownKeys(attributes);
    if (keys.length < 2 || keys.length > 3 ||
        keys.some((key) => typeof key !== "string" || !ALLOWED_FIELDS.has(key))) return NONE;
    const tagName = ownData(attributes, "tagName");
    if (typeof tagName !== "string" || tagName.toLowerCase() !== "object") return NONE;
    const data = normalizedObjectData(ownData(attributes, "data"));
    if (data === null) return NONE;

    const type = ownData(attributes, "type");
    if (Object.hasOwn(attributes, "type")) {
      if (!isValidDeclaredDownloadMime(type)) return NONE;
      const mime = detectPdfCandidate({ mimeType: type });
      // An explicit non-PDF type vetoes misleading .pdf data attributes.
      return mime.isPdfCandidate && mime.evidence === "mime-type" ?
        Object.freeze({ isPdfCandidate: true, evidence: "object-type", authorizesOpen: false }) : NONE;
    }
    const path = detectPdfCandidate({ url: data });
    return path.isPdfCandidate && path.evidence === "url-path" ?
      Object.freeze({ isPdfCandidate: true, evidence: "object-data", authorizesOpen: false }) : NONE;
  } catch {
    // Malformed input and hostile proxy traps fail closed without logging data.
    return NONE;
  }
}
