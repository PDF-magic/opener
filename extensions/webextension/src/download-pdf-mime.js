import { isValidDeclaredDownloadMime } from "./download-mime.js";
import { detectPdfCandidate } from "./pdf-detection.js";

// Pure, metadata-only classification. Browser MIME declarations are not
// trusted content identity, scanner verdicts, or permission to open a file.
function ownValue(record, key) {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  return descriptor && Object.hasOwn(descriptor, "value")
    ? descriptor.value : undefined;
}

/**
 * Classify an exact { id, mime } record returned by the already permission-
 * checked retrieveCompletedDownloadMime API. The MIME-specific classification
 * reuses the shared PDF detector; filenames and URLs are deliberately absent.
 *
 * Returns a frozen, path-free classification or null for malformed input.
 * A true classification does NOT authorize scans, opening, or native access.
 */
export function detectCompletedDownloadPdfMime(record) {
  try {
    if (!record || typeof record !== "object" || Array.isArray(record) ||
        ![Object.prototype, null].includes(Object.getPrototypeOf(record)) ||
        Reflect.ownKeys(record).length !== 2 ||
        !Object.hasOwn(record, "id") || !Object.hasOwn(record, "mime")) {
      return null;
    }
    const id = ownValue(record, "id");
    const mime = ownValue(record, "mime");
    if (!Number.isSafeInteger(id) || id < 0 ||
        !isValidDeclaredDownloadMime(mime)) return null;

    const classification = detectPdfCandidate({ mimeType: mime });
    const isPdfMime = classification.isPdfCandidate &&
      classification.evidence === "mime-type";
    return Object.freeze({
      id,
      isPdfMime,
      evidence: isPdfMime ? "mime-type" : "none",
      authorizesOpen: false
    });
  } catch {
    // Hostile browser objects or proxy traps must never leak metadata.
    return null;
  }
}
