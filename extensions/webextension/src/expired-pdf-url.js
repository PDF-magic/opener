// Handle expired or permanently unavailable remote PDF links without network
// access. A trusted browser adapter must verify provenance before any action.
export const EXPIRED_PDF_URL_FAILURE_CODES = Object.freeze({
  http: Object.freeze([403, 404, 410]),
  expiry: "DEADLINE_PASSED"
});

const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const EVENT_FIELDS = Object.freeze(["requestId", "downloadId", "kind", "code"]);
const SOURCE_FIELDS = Object.freeze([
  "requestId", "downloadId", "selectionId", "resourceId",
  "expiresAtMs", "observedAtMs", "verified"
]);
const UNAVAILABLE = Object.freeze({
  status: "unavailable", reason: "unverified",
  scanVerified: false, authorizesScan: false, authorizesOpen: false,
  automaticallyRetry: false, requiresNewConsent: true
});
const ENDED = Object.freeze({
  status: "ended", reason: "handler-disposed",
  scanVerified: false, authorizesScan: false, authorizesOpen: false,
  automaticallyRetry: false, requiresNewConsent: true
});
const EXPIRED_MESSAGE =
  "This PDF link has expired. Reload the website, select a new link, " +
  "and explicitly request Scan This PDF again.";
const GONE_MESSAGE =
  "This PDF link is no longer available. Return to the website to obtain " +
  "a new link, then explicitly request Scan This PDF again.";

function own(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function exactRecord(value, fields) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return null;
  const keys = Reflect.ownKeys(value);
  if (keys.length !== fields.length ||
      !keys.every(key => typeof key === "string" && fields.includes(key))) return null;
  const result = Object.create(null);
  for (const key of fields) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !Object.hasOwn(descriptor, "value")) return null;
    result[key] = descriptor.value;
  }
  return result;
}

function validDownloadId(value) {
  return value === null || (Number.isSafeInteger(value) && value >= 0);
}

function expiredSource(value, event) {
  const source = exactRecord(value, SOURCE_FIELDS);
  if (!source || source.requestId !== event.requestId ||
      source.downloadId !== event.downloadId ||
      typeof source.selectionId !== "string" || !ID.test(source.selectionId) ||
      source.selectionId === source.requestId ||
      typeof source.resourceId !== "string" || !ID.test(source.resourceId) ||
      source.resourceId === source.requestId ||
      source.verified !== true ||
      !Number.isSafeInteger(source.observedAtMs) || source.observedAtMs < 0 ||
      !(source.expiresAtMs === null ||
        (Number.isSafeInteger(source.expiresAtMs) && source.expiresAtMs > 0))) return null;
  return Object.freeze({
    expiredByDeadline: source.expiresAtMs !== null &&
      source.observedAtMs >= source.expiresAtMs
  });
}

function failureReason(event, source) {
  if (event.kind === "http" && event.code === 410) return "gone";
  if (source.expiredByDeadline && (
    (event.kind === "http" && (event.code === 403 || event.code === 404)) ||
    (event.kind === "expiry" && event.code === EXPIRED_PDF_URL_FAILURE_CODES.expiry)
  )) return "expired";
  return null;
}

/**
 * A passive failure-veto for a previously authenticated Scan This PDF attempt.
 *
 * The injected coordinator's own readVerifiedRemotePdfUrlSource(reference)
 * function MUST synchronously authenticate the response, current selection
 * and opaque resource and return exact scalar fields in SOURCE_FIELDS. Its
 * expiresAtMs/observedAtMs are trusted metadata, never parsed from a URL or
 * copied unverified from a page. HTTP 403 and 404 are ambiguous and become
 * expiry failures ONLY with independent, already elapsed expiry evidence.
 * HTTP 410 is a permanently unavailable resource even without a deadline.
 *
 * A verified failed attempt is blocked permanently within this handler.
 * The UI may suggest selecting a NEW document link and requesting fresh user
 * consent, but cannot refresh a signed URL or retry a download automatically.
 * No result here grants scanner approval or permission to open a PDF.
 */
export function createExpiredPdfUrlHandler(coordinator = null) {
  const blocked = new Map();
  let disposed = false;

  function observeFailure(candidate) {
    if (disposed) return ENDED;
    try {
      const event = exactRecord(candidate, EVENT_FIELDS);
      if (!event || typeof event.requestId !== "string" ||
          !ID.test(event.requestId) || !validDownloadId(event.downloadId) ||
          !((event.kind === "http" &&
              EXPIRED_PDF_URL_FAILURE_CODES.http.includes(event.code)) ||
            (event.kind === "expiry" &&
              event.code === EXPIRED_PDF_URL_FAILURE_CODES.expiry))) {
        return UNAVAILABLE;
      }
      const read = own(coordinator, "readVerifiedRemotePdfUrlSource");
      if (typeof read !== "function") return UNAVAILABLE;
      const reference = Object.freeze({
        requestId: event.requestId, downloadId: event.downloadId
      });
      const source = expiredSource(read.call(coordinator, reference), event);
      if (!source) return UNAVAILABLE;
      // An earlier verified expiration permanently vetoes this attempt.
      // A later ambiguous 403/404 cannot overwrite or remove the block.
      if (blocked.has(event.requestId)) return blocked.get(event.requestId);
      const reason = failureReason(event, source);
      if (!reason) return UNAVAILABLE;
      if (blocked.size >= 256) return UNAVAILABLE;

      const response = Object.freeze({
        status: "expired-document-url", reason,
        message: reason === "gone" ? GONE_MESSAGE : EXPIRED_MESSAGE,
        requestId: event.requestId, downloadId: event.downloadId,
        requiresNewDocumentLink: true, requiresNewConsent: true,
        automaticallyRetry: false, scanVerified: false,
        authorizesScan: false, authorizesOpen: false
      });
      // Latch first; a missing or throwing notification cannot unblock.
      blocked.set(event.requestId, response);
      try {
        const notify = own(coordinator, "notifyExpiredPdfUrl");
        if (typeof notify === "function") notify.call(coordinator, response);
      } catch { /* Never expose source URLs, query tokens or browser errors. */ }
      return response;
    } catch {
      return UNAVAILABLE;
    }
  }

  // A false result is not authorization to fetch, scan, or open: native
  // scanner readiness and fresh identity/consent checks still apply.
  function isBlocked(requestId) {
    if (disposed || typeof requestId !== "string" || !ID.test(requestId)) return true;
    return blocked.has(requestId);
  }

  function dispose() {
    disposed = true;
    blocked.clear();
    return ENDED;
  }

  return Object.freeze({ observeFailure, isBlocked, dispose });
}
