import { getPdfInterceptionPointAssessment } from "./pdf-interception-point-assessment.js";

// A dormant handoff contract, not a browser event listener or scan result
// verifier. The currently shipped extension has no active interception.
export const POST_SCAN_BROWSING_RESTORATION_MODES = Object.freeze([
  "original-page", "buffered-pdf-response"
]);

const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const REQUEST = ["scanRequestId", "holdId", "tabId"];
const HOLD = [
  ...REQUEST, "documentId", "browserId", "mode", "holdActive",
  "permissionGranted", "browserHoldVerified", "nativeSessionAuthenticated",
  "scanComplete", "scanVerified", "scanStatus", "pdfIdentityVerified",
  "originalPageAvailable", "verifiedBytesRetained", "nativeReleaseApproved"
];
const ACK = ["accepted", ...REQUEST];
const MAX_ATTEMPTS = 128;
const status = (name, requested = false) => Object.freeze({
  status: name, restorationRequested: requested, browsingRestored: false,
  automaticInterceptionEnabled: false, authorizesOpen: false
});
const INVALID = status("not-requested");
const UNAVAILABLE = status("unavailable");
const DUPLICATE = status("duplicate");
const ENDED = status("ended");
const SUBMITTED = status("restore-request-submitted", true);

function own(value, key) {
  if (value === null || (typeof value !== "object" &&
      typeof value !== "function")) return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ?
    descriptor.value : undefined;
}
function exact(value, fields) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
  const keys = Reflect.ownKeys(value);
  return keys.length === fields.length &&
    keys.every(key => typeof key === "string" && fields.includes(key)) &&
    fields.every(key => {
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      return descriptor && Object.hasOwn(descriptor, "value");
    });
}
function validRequest(request) {
  return exact(request, REQUEST) &&
    ID.test(own(request, "scanRequestId")) &&
    ID.test(own(request, "holdId")) &&
    own(request, "scanRequestId") !== own(request, "holdId") &&
    Number.isSafeInteger(own(request, "tabId")) &&
    own(request, "tabId") >= 0;
}

function verifiedHold(value, reference) {
  if (!exact(value, HOLD) || REQUEST.some(key =>
    own(value, key) !== reference[key]) ||
    !ID.test(own(value, "documentId")) ||
    own(value, "documentId") === reference.scanRequestId ||
    own(value, "documentId") === reference.holdId ||
    own(value, "holdActive") !== true ||
    own(value, "permissionGranted") !== true ||
    own(value, "browserHoldVerified") !== true ||
    own(value, "nativeSessionAuthenticated") !== true ||
    own(value, "scanComplete") !== true ||
    own(value, "scanVerified") !== true ||
    own(value, "scanStatus") !== "clean" ||
    own(value, "pdfIdentityVerified") !== true) return null;

  const browserId = own(value, "browserId");
  const assessment = getPdfInterceptionPointAssessment(browserId);
  if (assessment.browserId !== browserId) return null;
  const mode = own(value, "mode");
  if (mode === "original-page") {
    // Reveal an already preserved page. Never re-fetch/replay the PDF URL.
    if (own(value, "originalPageAvailable") !== true ||
        own(value, "verifiedBytesRetained") !== false ||
        own(value, "nativeReleaseApproved") !== false) return null;
  } else if (mode === "buffered-pdf-response") {
    // Only a separately validated Firefox response-stream implementation
    // may release the very bytes scanned. Never navigate to the URL again.
    if (browserId !== "firefox" ||
        assessment.responseBodyStreamPoint !==
          "firefox-response-filter-with-additional-grants" ||
        own(value, "verifiedBytesRetained") !== true ||
        own(value, "nativeReleaseApproved") !== true ||
        own(value, "originalPageAvailable") !== false) return null;
  } else return null;

  return Object.freeze({
    scanRequestId: reference.scanRequestId, holdId: reference.holdId,
    tabId: reference.tabId, documentId: own(value, "documentId"), mode,
    browserId
  });
}
function sameHold(a, b) {
  return Boolean(a && b && Object.keys(a).every(key => a[key] === b[key]));
}

/**
 * Optional post-scan browsing restoration for a FUTURE authenticated hold.
 * The coordinator must supply browserRestorationReady, synchronously
 * readVerifiedBrowsingHold(reference), and asynchronously
 * requestRestoreHeldBrowsing(reference). All trusted claims MUST be derived
 * from its own live browser/native hold and complete, clean native result,
 * not from page content, a caller boolean, download metadata, or a popup.
 *
 * The final callback must recheck hold ownership, permissions, PDF byte
 * identity, native policy, and tab/document identity at the actual handoff.
 * "original-page" only reveals the intact existing HTML document; the
 * Firefox-only buffered mode releases the SAME verified held response with
 * separate native approval, never a new request or unverified PDF viewer.
 *
 * This module does not navigate tabs, grant opening, install permissions,
 * register listeners, or claim a scan or browsing restoration occurred.
 */
export function createPostScanBrowsingRestoration(coordinator = null) {
  const attempted = new Set();
  let disposed = false;
  let generation = 0;

  async function restore(request) {
    if (disposed) return ENDED;
    try {
      if (!validRequest(request)) return INVALID;
      const reference = Object.freeze({
        scanRequestId: own(request, "scanRequestId"),
        holdId: own(request, "holdId"),
        tabId: own(request, "tabId")
      });
      const key = reference.scanRequestId + ":" + reference.holdId;
      if (attempted.has(key)) return DUPLICATE;
      if (attempted.size >= MAX_ATTEMPTS ||
          own(coordinator, "browserRestorationReady") !== true) return UNAVAILABLE;
      const read = own(coordinator, "readVerifiedBrowsingHold");
      const submit = own(coordinator, "requestRestoreHeldBrowsing");
      if (typeof read !== "function" || typeof submit !== "function") {
        return UNAVAILABLE;
      }
      const before = verifiedHold(read.call(coordinator, reference), reference);
      if (!before) return UNAVAILABLE;

      // Reserve before the asynchronous submission to prevent duplicate
      // release/replay, even if a previous outcome becomes unknown.
      attempted.add(key);
      const ticket = generation;
      const pending = submit.call(coordinator, before);
      if (!pending || typeof pending.then !== "function") return UNAVAILABLE;
      const acknowledgment = await pending;
      if (disposed || ticket !== generation ||
          own(coordinator, "browserRestorationReady") !== true ||
          own(coordinator, "readVerifiedBrowsingHold") !== read ||
          own(coordinator, "requestRestoreHeldBrowsing") !== submit ||
          !exact(acknowledgment, ACK) ||
          own(acknowledgment, "accepted") !== true ||
          REQUEST.some(field => own(acknowledgment, field) !== reference[field])) {
        return UNAVAILABLE;
      }
      const after = verifiedHold(read.call(coordinator, reference), reference);
      return sameHold(before, after) ? SUBMITTED : UNAVAILABLE;
    } catch {
      // Browser/native errors can contain private URLs or local paths.
      return UNAVAILABLE;
    }
  }
  function dispose() {
    disposed = true;
    generation += 1;
    attempted.clear();
    return ENDED;
  }
  return Object.freeze({ restore, dispose });
}
