// A strict, passive schema for explicit Scan This PDF request *metadata*.
// A validated descriptor is not a native scan command, file identity,
// authenticated user gesture, scanner verdict, or opening authorization.
export const EXPLICIT_PDF_SCAN_REQUEST_VERSION = 1;
export const EXPLICIT_PDF_SCAN_REQUEST_FIELDS = Object.freeze([
  "version", "requestId", "source", "tabId", "frameId",
  "selectionId", "userInitiated"
]);
export const EXPLICIT_PDF_SCAN_REQUEST_SOURCES = Object.freeze([
  "toolbar", "pdf-link", "embedded-pdf"
]);

const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const NONE = null;

function flatData(record) {
  if (record === null || typeof record !== "object" || Array.isArray(record) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(record))) {
    return null;
  }
  const keys = Reflect.ownKeys(record);
  if (keys.length !== EXPLICIT_PDF_SCAN_REQUEST_FIELDS.length) return null;
  const fields = Object.create(null);
  for (const key of keys) {
    if (typeof key !== "string" ||
        !EXPLICIT_PDF_SCAN_REQUEST_FIELDS.includes(key)) return null;
    const descriptor = Object.getOwnPropertyDescriptor(record, key);
    if (!descriptor || !Object.hasOwn(descriptor, "value")) return null;
    fields[key] = descriptor.value;
  }
  if (!EXPLICIT_PDF_SCAN_REQUEST_FIELDS.every(key => Object.hasOwn(fields, key))) {
    return null;
  }
  return fields;
}

/**
 * Validate the minimal, browser-neutral metadata a future trusted adapter
 * must associate with an explicit "Scan This PDF" invocation.
 *
 * requestId: a bounded, per-attempt correlation key, NOT native authorization.
 * source: toolbar, PDF-link menu, or embedded-PDF menu.
 * tabId/frameId: browser-owned location; toolbar is always the top frame.
 * selectionId: opaque selection identifier minted by the trusted adapter,
 *   NOT a page URL, local path, PDF content, or standalone security token.
 * userInitiated: must be true, but a supplied boolean alone never proves an
 *   actual browser user gesture.
 *
 * The caller is responsible for authenticating browser/selection provenance,
 * validating document freshness and access permissions, and resolving the
 * selected PDF to a native-verified stable local file. Native code must enforce
 * scan-before-open, ClamAV freshness, quarantine and file-identity gates.
 * The returned descriptor must never be forwarded as a native scan command.
 */
export function describeExplicitPdfScanRequest(details) {
  try {
    const record = flatData(details);
    if (!record ||
        record.version !== EXPLICIT_PDF_SCAN_REQUEST_VERSION ||
        !EXPLICIT_PDF_SCAN_REQUEST_SOURCES.includes(record.source) ||
        typeof record.requestId !== "string" || !ID.test(record.requestId) ||
        typeof record.selectionId !== "string" || !ID.test(record.selectionId) ||
        record.selectionId === record.requestId ||
        !Number.isSafeInteger(record.tabId) || record.tabId < 0 ||
        !Number.isSafeInteger(record.frameId) || record.frameId < 0 ||
        (record.source === "toolbar" && record.frameId !== 0) ||
        record.userInitiated !== true) return NONE;

    // Detached, immutable scalar metadata only. Never return page URLs, file
    // paths, bytes, MIME claims, scanner output or a permission to scan/open.
    return Object.freeze({
      version: EXPLICIT_PDF_SCAN_REQUEST_VERSION,
      requestId: record.requestId,
      source: record.source,
      tabId: record.tabId,
      frameId: record.frameId,
      selectionId: record.selectionId,
      userInitiated: true,
      status: "metadata-only",
      requiresTrustedSelection: true,
      requiresNativeFileValidation: true,
      scanVerified: false,
      authorizesScan: false,
      authorizesOpen: false
    });
  } catch {
    // Untrusted getters/proxy traps and malformed metadata fail closed.
    return NONE;
  }
}
