import { detectPdfCandidate } from "./pdf-detection.js";

// Only a passive hint that browser MIME disagrees with the final filename.
// Neither a declaration nor a filename verifies PDF bytes or scan safety.
const MAX_MIME_LENGTH = 255;
const MAX_FILENAME_LENGTH = 4096;
const MIME_PATTERN = /^[A-Za-z0-9!#$%&'*+.^_|~-]+\/[A-Za-z0-9!#$%&'*+.^_|~-]+(?: *; *[A-Za-z0-9!#$%&'*+.^_|~-]+ *= *(?:[A-Za-z0-9!#$%&'*+.^_|~-]+|"[^"]*"))*$/u;

function own(value, key) {
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function record(value, field) {
  try {
    if (value === null || typeof value !== "object" || Array.isArray(value) ||
        ![Object.prototype, null].includes(Object.getPrototypeOf(value)) ||
        Reflect.ownKeys(value).length !== 2) return null;
    const id = own(value, "id");
    const data = own(value, field);
    if (!Number.isSafeInteger(id) || id < 0 || typeof data !== "string") return null;
    return { id, data };
  } catch {
    // A hostile Proxy must not execute a consumer callback or leak metadata.
    return null;
  }
}

/**
 * Compare results of the existing permission-checked, exact-ID completed
 * download filename and MIME lookups. No browser APIs, bytes or paths are
 * read here; pass records for the SAME completed browser download.
 *
 * The browser may report PDF MIME for a .txt, .bin, .pdf.exe, or extensionless
 * filename. This is only an untrusted candidate signal, not content proof.
 */
export function detectMisleadingPdfExtension(mimeRecord, filenameRecord) {
  const declared = record(mimeRecord, "mime");
  const named = record(filenameRecord, "filename");
  if (!declared || !named || declared.id !== named.id) return null;
  const { data: mime } = declared;
  const { data: filename } = named;
  if (!mime || mime.length > MAX_MIME_LENGTH ||
      /[\u0000-\u001f\u007f]/u.test(mime) || !MIME_PATTERN.test(mime) ||
      !filename || filename.length > MAX_FILENAME_LENGTH ||
      /[\u0000-\u001f\u007f]/u.test(filename) ||
      /^[A-Za-z][A-Za-z0-9+.-]*:\/\//u.test(filename)) return null;

  const basename = filename.split(/[\\/]/u).at(-1);
  if (!basename || basename === "." || basename === "..") return null;

  const pdfMime = detectPdfCandidate({ mimeType: mime }).evidence === "mime-type";
  const pdfSuffix = /^[^.].*\.pdf$/iu.test(basename);
  return Object.freeze({
    id: declared.id,
    isPdfCandidate: pdfMime,
    hasMisleadingExtension: pdfMime && !pdfSuffix,
    evidence: pdfMime ? "browser-pdf-mime" : "none",
    authorizesOpen: false
  });
}
