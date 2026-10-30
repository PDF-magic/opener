// Handle authentication-related failures for explicitly selected remote PDFs.
// Passive and fail-closed: no browser listeners, network, credentials, scans or
// opening behavior. A trusted browser adapter must supply verified correlation.
export const REMOTE_PDF_AUTH_FAILURE_CODES = Object.freeze({
  http: Object.freeze([401, 403, 407]),
  download: Object.freeze(["SERVER_UNAUTHORIZED", "SERVER_FORBIDDEN"])
});

const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const expectedFailure = Object.freeze(["requestId", "downloadId", "kind", "code"]);
const expectedTransfer = Object.freeze([
  "requestId", "downloadId", "selectionId", "verified"
]);
const reasons = Object.freeze({
  "sign-in-required": Object.freeze({
    status: "authentication-required",
    message: "Sign in to the website in your browser, then start a new Scan This PDF request."
  }),
  "access-denied": Object.freeze({
    status: "access-denied",
    message: "The website denied access to this PDF. Check your access in the browser before starting a new request."
  }),
  "proxy-sign-in-required": Object.freeze({
    status: "authentication-required",
    message: "Network proxy authentication is required. Sign in through your browser or network settings before retrying manually."
  })
});
const unavailable = Object.freeze({
  status: "unavailable", reason: "unverified",
  scanVerified: false, authorizesScan: false, authorizesOpen: false,
  automaticallyRetry: false
});
const ended = Object.freeze({
  status: "ended", reason: "handler-disposed",
  scanVerified: false, authorizesScan: false, authorizesOpen: false,
  automaticallyRetry: false
});

function own(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function record(value, keys) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return null;
  const present = Reflect.ownKeys(value);
  if (present.length !== keys.length ||
      !present.every(key => typeof key === "string" && keys.includes(key))) {
    return null;
  }
  const fields = Object.create(null);
  for (const key of keys) {
    const desc = Object.getOwnPropertyDescriptor(value, key);
    if (!desc || !Object.hasOwn(desc, "value")) return null;
    fields[key] = desc.value;
  }
  return fields;
}

function failureReason(kind, code) {
  if (kind === "http") {
    if (code === 401) return "sign-in-required";
    if (code === 403) return "access-denied";
    if (code === 407) return "proxy-sign-in-required";
  }
  if (kind === "download") {
    if (code === "SERVER_UNAUTHORIZED") return "sign-in-required";
    if (code === "SERVER_FORBIDDEN") return "access-denied";
  }
  return null;
}

/**
 * Interpret a browser-owned HTTP failure or downloads.onChanged interruption
 * only after a trusted coordinator associates it with an active Scan This PDF
 * request. A page-provided response status, error text or requestId is NOT
 * trustworthy. The coordinator's own readVerifiedRemotePdfTransfer callback
 * must check current provenance and provide an exact synchronous record:
 * { requestId, downloadId, selectionId, verified: true }.
 *
 * Download errors require a numeric download ID. HTTP failures may arrive
 * before a download ID is allocated and use downloadId: null. Neither case
 * obtains credentials, retries a fetch, restarts a download or opens a file.
 * When verified, the request is permanently blocked in this handler. A new
 * attempt needs a new request ID, fresh consent and browser authentication.
 */
export function createRemotePdfAuthenticationFailureHandler(coordinator = null) {
  const blocked = new Map();
  let disposed = false;

  function observeFailure(event) {
    if (disposed) return ended;
    try {
      const failure = record(event, expectedFailure);
      if (!failure || typeof failure.requestId !== "string" ||
          !ID.test(failure.requestId) ||
          !(failure.downloadId === null ||
            (Number.isSafeInteger(failure.downloadId) && failure.downloadId >= 0)) ||
          (failure.kind === "download" && failure.downloadId === null)) {
        return unavailable;
      }
      const reason = failureReason(failure.kind, failure.code);
      if (!reason) return unavailable;
      const read = own(coordinator, "readVerifiedRemotePdfTransfer");
      if (typeof read !== "function") return unavailable;
      const correlation = Object.freeze({
        requestId: failure.requestId, downloadId: failure.downloadId
      });
      const trusted = record(read.call(coordinator, correlation), expectedTransfer);
      if (!trusted || trusted.requestId !== failure.requestId ||
          trusted.downloadId !== failure.downloadId ||
          typeof trusted.selectionId !== "string" ||
          !ID.test(trusted.selectionId) ||
          trusted.selectionId === trusted.requestId ||
          trusted.verified !== true) return unavailable;

      if (blocked.has(failure.requestId)) return blocked.get(failure.requestId);
      if (blocked.size >= 256) return unavailable;

      const details = reasons[reason];
      const result = Object.freeze({
        status: details.status, reason, message: details.message,
        requestId: failure.requestId, downloadId: failure.downloadId,
        manualRetryRequired: true, automaticallyRetry: false,
        scanVerified: false, authorizesScan: false, authorizesOpen: false
      });
      // Latch before displaying a notice. A throwing UI cannot unblock it.
      blocked.set(failure.requestId, result);
      try {
        const notify = own(coordinator, "notifyRemotePdfAuthenticationFailure");
        if (typeof notify === "function") notify.call(coordinator, result);
      } catch { /* no private browser/native error details escape */ }
      return result;
    } catch {
      return unavailable;
    }
  }

  // A false result is NOT a positive permission to scan or open. Every later
  // transfer/completion must still pass the independent native safety gates.
  function isBlocked(requestId) {
    if (disposed || typeof requestId !== "string" || !ID.test(requestId)) return true;
    return blocked.has(requestId);
  }

  function dispose() {
    disposed = true;
    blocked.clear();
    return ended;
  }

  return Object.freeze({ observeFailure, isBlocked, dispose });
}
