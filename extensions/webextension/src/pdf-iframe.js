import { detectPdfCandidate } from "./pdf-detection.js";

// Passive classification of a single, explicitly supplied HTML iframe record.
// A future, separately permissioned adapter must provide this metadata; this
// module never walks a page DOM, observes frames or starts a browser action.
const NONE = Object.freeze({
  isPdfCandidate: false, evidence: "none", authorizesOpen: false
});
const YES = Object.freeze({
  isPdfCandidate: true, evidence: "iframe-src", authorizesOpen: false
});
const ALLOWED_FIELDS = new Set(["tagName", "src", "documentUrl", "srcdoc"]);
const MAX_URL_LENGTH = 8192;

function readFields(input) {
  if (input === null || typeof input !== "object" || Array.isArray(input) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(input))) return null;
  const fields = Object.create(null);
  for (const key of Reflect.ownKeys(input)) {
    if (typeof key !== "string" || !ALLOWED_FIELDS.has(key)) return null;
    const descriptor = Object.getOwnPropertyDescriptor(input, key);
    if (!descriptor || !Object.hasOwn(descriptor, "value")) return null;
    fields[key] = descriptor.value;
  }
  return fields;
}

/**
 * Identify PDF candidates referenced by a normalized HTML <iframe> element.
 * `src` is the element's literal src attribute (not page HTML); `documentUrl`
 * is the trusted containing document URL when relative resolution is needed.
 * `srcdoc`, when present, takes precedence over src and is not inspected.
 * A page-authored MIME/type claim alone is never PDF evidence.
 *
 * No DOM traversal, host permission, network request, scan or open occurs.
 * Only a frozen, URL-free candidate flag is returned. The caller is responsible
 * for verifying the source and any later response bytes and scan-before-open.
 */
export function detectPdfIframe(input) {
  try {
    const fields = readFields(input);
    if (!fields || fields.tagName !== "iframe" && fields.tagName !== "IFRAME" ||
        Object.hasOwn(fields, "srcdoc") ||
        typeof fields.src !== "string" || !fields.src.trim() ||
        fields.src.length > MAX_URL_LENGTH ||
        /[\u0000-\u001f\u007f]/u.test(fields.src)) return NONE;

    // URL resolution requires an HTTP(S) containing page for relative paths.
    // The source may be absolute if no documentUrl is provided.
    let base;
    if (Object.hasOwn(fields, "documentUrl")) {
      if (typeof fields.documentUrl !== "string" ||
          fields.documentUrl.length > MAX_URL_LENGTH ||
          /[\u0000-\u0020\u007f]/u.test(fields.documentUrl)) return NONE;
      base = new URL(fields.documentUrl);
      if (!["http:", "https:"].includes(base.protocol) || !base.hostname) return NONE;
    }
    const resolved = new URL(fields.src, base);
    if (!["http:", "https:"].includes(resolved.protocol) || !resolved.hostname ||
        resolved.href.length > MAX_URL_LENGTH) return NONE;
    const result = detectPdfCandidate({ url: resolved.href });
    return result.isPdfCandidate && result.evidence === "url-path" ? YES : NONE;
  } catch {
    // Malformed inputs or hostile proxies fail closed without logging URLs.
    return NONE;
  }
}
