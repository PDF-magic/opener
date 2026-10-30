// An accessible Blob, not its URL or declared MIME alone, supplies evidence.
// This inert helper trusts no page event or URL-to-Blob association by itself.
const NONE = Object.freeze({ isPdfCandidate: false, evidence: "none", authorizesOpen: false });
const PDF = Object.freeze({ isPdfCandidate: true, evidence: "blob-signature", authorizesOpen: false });
const UUID = "[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}";
const URL_PATTERN = new RegExp("^blob:(https?:\\/\\/[^/?#]+|null)\\/(" + UUID + ")$");
const SIGNATURE = [37, 80, 68, 70, 45]; // %PDF-

function ownData(record, key) {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function supportedBlobUrl(value) {
  if (typeof value !== "string" || value.length > 8192 ||
      /[\u0000-\u0020\u007f]/u.test(value)) return false;
  const match = URL_PATTERN.exec(value);
  if (!match || new URL(value).protocol !== "blob:") return false;
  if (match[1] === "null") return true;
  const origin = new URL(match[1]);
  return origin.origin === match[1] && !origin.username && !origin.password;
}

/**
 * A separately authorized browser integration must verify the event and the
 * actual Blob-to-URL association before calling this classifier. Only reads
 * five bytes; does not validate PDF structures, scan, open, fetch, log or grant
 * permissions. Candidate detection never bypasses native scan enforcement.
 */
export async function detectBlobPdfContent(details, blob) {
  try {
    if (details === null || typeof details !== "object" ||
        Array.isArray(details) ||
        ![Object.prototype, null].includes(Object.getPrototypeOf(details))) return NONE;
    const tabId = ownData(details, "tabId");
    const frameId = ownData(details, "frameId");
    if (!Number.isSafeInteger(tabId) || tabId < 0 ||
        !Number.isSafeInteger(frameId) || frameId < 0 ||
        !supportedBlobUrl(ownData(details, "url"))) return NONE;

    // Native built-ins perform Blob brand checks without invoking overridden
    // instance getters or methods supplied by an untrusted page.
    const size = Object.getOwnPropertyDescriptor(Blob.prototype, "size").get.call(blob);
    const type = Object.getOwnPropertyDescriptor(Blob.prototype, "type").get.call(blob);
    if (!Number.isSafeInteger(size) || size < SIGNATURE.length ||
        !["", "application/pdf", "application/x-pdf",
          "application/octet-stream", "binary/octet-stream"].includes(type)) return NONE;
    const prefix = Blob.prototype.slice.call(blob, 0, SIGNATURE.length);
    const bytes = new Uint8Array(await Blob.prototype.arrayBuffer.call(prefix));
    return bytes.length === SIGNATURE.length &&
      SIGNATURE.every((byte, index) => bytes[index] === byte) ? PDF : NONE;
  } catch {
    // Invalid/hostile metadata and unsupported Blob APIs fail closed.
    return NONE;
  }
}
