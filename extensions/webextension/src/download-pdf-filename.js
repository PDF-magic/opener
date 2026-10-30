import { detectPdfCandidate } from "./pdf-detection.js";

// An untrusted browser filename is a hint, never a PDF validation, scanner
// verdict or authorization to read, scan or open a downloaded file.
const MAX_PATH_LENGTH = 4096;
const MAX_COMPONENT_LENGTH = 512;
const nonCandidate = (id) => Object.freeze({ id, isPdfFilename: false, authorizesOpen: false });

/**
 * Classify the final component of the already permission-checked
 * { id, filename } record from retrieveCompletedDownloadFilename().
 * Supports both POSIX and Windows separators, with no filesystem calls,
 * path exposure, filename persistence, browser access or native messages.
 * Invalid/hostile objects fail closed. A suffix match is not proof of PDF
 * content or permission to open; callers must still honor all scan gates.
 */
export function detectCompletedPdfFilename(record) {
  try {
    if (record === null || typeof record !== "object" || Array.isArray(record) ||
        ![Object.prototype, null].includes(Object.getPrototypeOf(record))) return null;
    const keys = Reflect.ownKeys(record);
    if (keys.length !== 2 || !keys.includes("id") || !keys.includes("filename")) return null;
    const idProperty = Object.getOwnPropertyDescriptor(record, "id");
    const filenameProperty = Object.getOwnPropertyDescriptor(record, "filename");
    if (!idProperty || !Object.hasOwn(idProperty, "value") ||
        !filenameProperty || !Object.hasOwn(filenameProperty, "value")) return null;
    const id = idProperty.value;
    const filename = filenameProperty.value;
    if (!Number.isSafeInteger(id) || id < 0 || typeof filename !== "string" ||
        filename.length === 0 || filename.length > MAX_PATH_LENGTH ||
        /[\u0000-\u001f\u007f]/u.test(filename) ||
        (/^[A-Za-z][A-Za-z0-9+.-]*:\/\//u.test(filename) ||
         /^(?:blob|data|javascript|file):/iu.test(filename))) return null;
    const name = filename.split(/[\\/]/u).at(-1);
    if (!name || name.length > MAX_COMPONENT_LENGTH) return nonCandidate(id);
    const result = detectPdfCandidate({ filename: name });
    return Object.freeze({
      id,
      isPdfFilename: result.isPdfCandidate && result.evidence === "filename",
      authorizesOpen: false
    });
  } catch {
    // Do not evaluate browser-supplied accessors or leak local paths.
    return null;
  }
}
