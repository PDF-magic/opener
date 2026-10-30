import { describeExplicitPdfScanRequest } from "./explicit-pdf-scan-request.js";

// Treat every signed PDF URL as a short-lived bearer credential. This module
// never registers listeners, fetches, logs, persists, scans or opens content.
export const SIGNED_PDF_URL_MIN_REMAINING_MS = 30_000;

const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const SOURCE_FIELDS = Object.freeze([
  "requestId", "tabId", "frameId", "selectionId", "resourceId",
  "url", "siteOrigin", "expiresAtMs", "verified",
  "signatureVerified", "permissionGranted"
]);
const result = Object.freeze(Object.fromEntries(
  ["not-requested", "unavailable", "expired", "duplicate", "ended", "handed-off"]
    .map(status => [status, Object.freeze({
      status, handoffRequested: status === "handed-off",
      requiresFreshSelection: status === "expired",
      requiresNewConsent: status !== "handed-off",
      automaticallyRetry: false, scanVerified: false,
      authorizesScan: false, authorizesOpen: false
    })])
));

function own(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  const prop = Object.getOwnPropertyDescriptor(value, key);
  return prop && Object.hasOwn(prop, "value") ? prop.value : undefined;
}
function method(value, key) {
  const fn = own(value, key);
  return typeof fn === "function" ? fn : null;
}
function exactRecord(value, fields) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return null;
  const keys = Reflect.ownKeys(value);
  if (keys.length !== fields.length ||
      !keys.every(key => typeof key === "string" && fields.includes(key))) return null;
  const data = Object.create(null);
  for (const key of fields) {
    const property = Object.getOwnPropertyDescriptor(value, key);
    if (!property || !Object.hasOwn(property, "value")) return null;
    data[key] = property.value;
  }
  return data;
}
function safeExactSignedUrl(raw, siteOrigin) {
  if (typeof raw !== "string" || raw.length < 10 || raw.length > 8192 ||
      /[\u0000-\u0020\u007f\\#]/u.test(raw) ||
      /%(?![a-f0-9]{2})/iu.test(raw) ||
      /%(?:0a|0d|7f)/iu.test(raw)) return false;
  const parsed = new URL(raw);
  return parsed.protocol === "https:" && Boolean(parsed.hostname) &&
    parsed.username === "" && parsed.password === "" &&
    parsed.hash === "" && parsed.href === raw &&
    parsed.origin === siteOrigin && siteOrigin.length <= 260 &&
    !parsed.hostname.endsWith(".") &&
    !["localhost", "127.0.0.1", "[::1]"].includes(parsed.hostname);
}
function trustedSelection(record, request) {
  const value = exactRecord(record, SOURCE_FIELDS);
  if (!value || value.requestId !== request.requestId ||
      value.tabId !== request.tabId || value.frameId !== request.frameId ||
      value.selectionId !== request.selectionId ||
      typeof value.resourceId !== "string" || !ID.test(value.resourceId) ||
      value.resourceId === request.requestId ||
      value.verified !== true || value.signatureVerified !== true ||
      value.permissionGranted !== true ||
      !Number.isSafeInteger(value.expiresAtMs) || value.expiresAtMs <= 0 ||
      typeof value.siteOrigin !== "string" ||
      !safeExactSignedUrl(value.url, value.siteOrigin)) return null;
  // Expiration is an independently verified property of this specific
  // signed resource, NOT an untrusted Expires/X-Amz-* query parameter.
  return Object.freeze({
    requestId: value.requestId, tabId: value.tabId, frameId: value.frameId,
    selectionId: value.selectionId, resourceId: value.resourceId,
    url: value.url, siteOrigin: value.siteOrigin,
    expiresAtMs: value.expiresAtMs
  });
}
function sameSelection(a, b) {
  return Boolean(a && b && SOURCE_FIELDS
    .filter(key => !["verified", "signatureVerified", "permissionGranted"].includes(key))
    .every(key => a[key] === b[key]));
}
function hasTimeToDownload(snapshot) {
  return Boolean(snapshot && snapshot.expiresAtMs > Date.now() +
    SIGNED_PDF_URL_MIN_REMAINING_MS);
}

/**
 * Hand off an authenticated current PDF's exact, short-lived signed URL.
 *
 * The trusted coordinator must have three own methods:
 * - readVerifiedSignedPdfSelection(reference): synchronous and network-free,
 *   with an independently authenticated current source and expiry timestamp.
 * - consumeVerifiedSignedPdfConsent(reference): Promise<true>, which atomically
 *   consumes a previously displayed, per-attempt consent approval.
 * - handoffVerifiedSignedPdfDownload({ ..., url }): Promise<{accepted:true}>,
 *   which owns origin/redirect checks, permission revocations and safe browser
 *   downloads. It must never log, persist, truncate, sort, decode or re-encode
 *   the signed URL, or let it reach native scan messages.
 *
 * This guard never recognizes signature or expiration from query names alone.
 * It returns no URL or credential and cannot grant a scan/open verdict.
 */
export function createSignedTemporaryPdfUrlHandoff(coordinator = null) {
  const attempted = new Set();
  let ended = false;
  let generation = 0;

  async function handoff(request) {
    if (ended) return result.ended;
    const details = describeExplicitPdfScanRequest(request);
    if (!details) return result["not-requested"];
    if (attempted.has(details.requestId)) return result.duplicate;
    if (attempted.size >= 256) return result.unavailable;
    attempted.add(details.requestId);
    const start = generation;
    try {
      if (own(coordinator, "signedTemporaryPdfReady") !== true) return result.unavailable;
      const read = method(coordinator, "readVerifiedSignedPdfSelection");
      const consume = method(coordinator, "consumeVerifiedSignedPdfConsent");
      const submit = method(coordinator, "handoffVerifiedSignedPdfDownload");
      if (!read || !consume || !submit) return result.unavailable;
      const reference = Object.freeze({
        requestId: details.requestId, tabId: details.tabId,
        frameId: details.frameId, selectionId: details.selectionId,
        source: details.source
      });
      const before = trustedSelection(read.call(coordinator, reference), details);
      if (!before) return result.unavailable;
      if (!hasTimeToDownload(before)) return result.expired;
      // The consent operation must be independently bound to this attempt,
      // verified selection and origin. A supplied userInitiated flag is not
      // evidence of a real gesture or a valid consent approval.
      const consent = consume.call(coordinator, Object.freeze({
        ...reference, resourceId: before.resourceId, siteOrigin: before.siteOrigin
      }));
      if (!consent || typeof consent.then !== "function") return result.unavailable;
      if ((await consent) !== true) return result.unavailable;
      if (ended || generation !== start ||
          own(coordinator, "signedTemporaryPdfReady") !== true ||
          method(coordinator, "readVerifiedSignedPdfSelection") !== read ||
          method(coordinator, "handoffVerifiedSignedPdfDownload") !== submit) {
        return result.unavailable;
      }
      const after = trustedSelection(read.call(coordinator, reference), details);
      if (!sameSelection(before, after)) return result.unavailable;
      if (!hasTimeToDownload(after)) return result.expired;
      // This is the only point where the opaque credential URL leaves the
      // trusted reader: the selected, consented transport callback only.
      const pending = submit.call(coordinator, Object.freeze({
        ...reference, resourceId: after.resourceId,
        siteOrigin: after.siteOrigin, url: after.url
      }));
      if (!pending || typeof pending.then !== "function") return result.unavailable;
      const receipt = await pending;
      if (ended || generation !== start || own(receipt, "accepted") !== true) {
        return result.unavailable;
      }
      return result["handed-off"];
    } catch {
      // Browser exceptions can contain signed tokens or private PDF paths.
      return result.unavailable;
    }
  }

  function dispose() {
    ended = true;
    generation++;
    attempted.clear();
    return result.ended;
  }

  return Object.freeze({ handoff, dispose });
}
