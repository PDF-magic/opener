import { detectPdfResponseMime } from "./pdf-response-mime.js";
import { detectPdfNavigation } from "./pdf-navigation.js";

// Passive identification only. A URL alone cannot prove that an
// extensionless response contains PDF data; a trusted browser-supplied
// main-frame response Content-Type is required for candidate evidence.
const NONE = Object.freeze({
  isPdfCandidate: false, evidence: "none", authorizesOpen: false
});
const MAX_URL_LENGTH = 8192;

function ownData(record, field) {
  const descriptor = Object.getOwnPropertyDescriptor(record, field);
  return descriptor && Object.hasOwn(descriptor, "value") ?
    descriptor.value : undefined;
}

function safeExtensionlessHttpUrl(raw) {
  if (typeof raw !== "string" || !raw.length || raw.length > MAX_URL_LENGTH ||
      /[\u0000-\u0020\u007f]/u.test(raw)) return false;
  const parsed = new URL(raw);
  if (!["http:", "https:"].includes(parsed.protocol) || !parsed.hostname ||
      parsed.username || parsed.password) return false;

  // A literal/encoded path suffix is not extensionless. Also reject malformed
  // percent escapes, encoded separators and controls rather than treating an
  // ambiguous filename as trustworthy extensionless evidence.
  const tail = decodeURIComponent(parsed.pathname.split("/").at(-1));
  return !/[\\/\u0000-\u001f\u007f]/u.test(tail) &&
    !/\.pdf$/iu.test(tail);
}

/**
 * Detect PDFs returned by trusted top-frame navigation responses even when
 * the response URL ends in /download, /view?id=..., .bin or another non-.pdf
 * suffix. Reuses the separately reviewed navigation and response MIME
 * classifiers; never guesses from a filename, URL query or page metadata.
 *
 * The caller must independently trust and authorize the browser event source.
 * No permission, network, scan or opening side effect occurs in this helper.
 */
export function detectExtensionlessPdfResponse(details) {
  try {
    if (details === null || typeof details !== "object" ||
        Array.isArray(details) ||
        ![Object.prototype, null].includes(Object.getPrototypeOf(details))) {
      return NONE;
    }
    const rawUrl = ownData(details, "url");
    if (!safeExtensionlessHttpUrl(rawUrl)) return NONE;

    // Use existing validated navigation context, but never allow URL-path
    // matching to substitute for affirmative PDF response MIME evidence.
    const urlResult = detectPdfNavigation(details);
    if (urlResult.isPdfCandidate) return NONE;
    const mimeResult = detectPdfResponseMime(details);
    return mimeResult.isPdfCandidate && mimeResult.evidence === "mime-type" ?
      mimeResult : NONE;
  } catch {
    // Fail closed for malformed browser events, accessors and proxy traps.
    // Never include or log private request URLs and response headers.
    return NONE;
  }
}
