import { detectPdfCandidate } from "./pdf-detection.js";

// Passive classification of explicitly normalized HTML <embed> attributes.
// This module never reads a page, grants a browser permission, or opens a PDF.
const NONE = Object.freeze({
  isPdfCandidate: false, evidence: "none", authorizesOpen: false
});
const ALLOWED = new Set(["tagName", "src", "type", "baseUrl"]);
const MAX_URL_LENGTH = 8192;
const MAX_TYPE_LENGTH = 256;

function metadata(input) {
  if (input === null || typeof input !== "object" || Array.isArray(input) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(input))) return null;
  const fields = Object.create(null);
  const keys = Reflect.ownKeys(input);
  if (keys.length > ALLOWED.size) return null;
  for (const key of keys) {
    if (typeof key !== "string" || !ALLOWED.has(key)) return null;
    const descriptor = Object.getOwnPropertyDescriptor(input, key);
    if (!descriptor || !Object.hasOwn(descriptor, "value")) return null;
    fields[key] = descriptor.value;
  }
  if (typeof fields.tagName !== "string" || fields.tagName.toLowerCase() !== "embed" ||
      typeof fields.src !== "string" || !fields.src ||
      fields.src.length > MAX_URL_LENGTH ||
      (fields.type !== undefined &&
        (typeof fields.type !== "string" || fields.type.length > MAX_TYPE_LENGTH)) ||
      (fields.baseUrl !== undefined &&
        (typeof fields.baseUrl !== "string" || fields.baseUrl.length > MAX_URL_LENGTH))) return null;
  return fields;
}

function safeHttpUrl(value, baseUrl) {
  // Reject URL-parser normalization ambiguities, controls and malformed escapes.
  if (/[\\\s\u0000-\u001f\u007f]/u.test(value) || /%(?![a-f\d]{2})/iu.test(value)) return null;
  const base = baseUrl === undefined ? undefined : new URL(baseUrl);
  if (base && (!["http:", "https:"].includes(base.protocol) ||
      !base.hostname || base.username || base.password ||
      /[\\\s\u0000-\u001f\u007f]/u.test(baseUrl) ||
      /%(?![a-f\d]{2})/iu.test(baseUrl))) return null;
  const url = new URL(value, base);
  if (!["http:", "https:"].includes(url.protocol) ||
      !url.hostname || url.username || url.password) return null;
  // Encoded separators or controls cannot become trusted extension evidence.
  for (const segment of url.pathname.split("/")) {
    if (/[\\/\u0000-\u001f\u007f]/u.test(decodeURIComponent(segment))) return null;
  }
  return url.href;
}

/**
 * Classify metadata explicitly attributed to an actual HTML <embed> element.
 * A future caller must authenticate the page/element source and obtain any
 * required consent and permission before supplying these four scalar fields.
 * Page-provided type and src are hints, never trusted response headers.
 *
 * @param {{tagName: string, src: string, type?: string, baseUrl?: string}} details
 * @returns {{isPdfCandidate: boolean, evidence: string, authorizesOpen: false}}
 */
export function detectPdfEmbedElement(details) {
  try {
    const fields = metadata(details);
    if (!fields) return NONE;
    const url = safeHttpUrl(fields.src, fields.baseUrl);
    if (!url) return NONE;
    const match = detectPdfCandidate({ url, mimeType: fields.type });
    if (!match.isPdfCandidate) return NONE;
    return Object.freeze({
      isPdfCandidate: true,
      evidence: match.evidence === "mime-type" ? "embed-type" : "embed-src",
      authorizesOpen: false
    });
  } catch {
    // Hostile metadata, proxy traps or malformed URLs fail closed without logs.
    return NONE;
  }
}
