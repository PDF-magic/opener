import { describeExplicitPdfScanRequest } from "./explicit-pdf-scan-request.js";
import { subscribeToPermissionRevocations } from "./permission-revocations.js";

// Passive boundary for the explicit Scan This PDF action. Even a host grant
// cannot bypass site/CORS policy, fetch data, authorize scanning or open a PDF.
export const CROSS_ORIGIN_PDF_MESSAGE =
  "This PDF is served from another website. Access is restricted unless the browser verifies permission for that exact site.";

const FIELDS = Object.freeze([
  "requestId", "tabId", "frameId", "selectionId", "resourceId",
  "documentOrigin", "resourceOrigin", "verified", "permissionGranted"
]);
const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const unavailable = Object.freeze({
  status: "unavailable", crossOrigin: false, sitePermissionVerified: false,
  requiresSitePermission: false, authorizesFetch: false,
  authorizesScan: false, authorizesOpen: false
});
const sameOrigin = Object.freeze({
  status: "same-origin", crossOrigin: false, sitePermissionVerified: false,
  requiresSitePermission: false, authorizesFetch: false,
  authorizesScan: false, authorizesOpen: false
});
const restricted = Object.freeze({
  status: "cross-origin-restricted", crossOrigin: true, sitePermissionVerified: false,
  requiresSitePermission: true, authorizesFetch: false,
  authorizesScan: false, authorizesOpen: false
});
const granted = Object.freeze({
  status: "cross-origin-site-grant-verified", crossOrigin: true, sitePermissionVerified: true,
  requiresSitePermission: false, authorizesFetch: false,
  authorizesScan: false, authorizesOpen: false
});

function own(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  const desc = Object.getOwnPropertyDescriptor(value, key);
  return desc && Object.hasOwn(desc, "value") ? desc.value : undefined;
}

function exact(value, expected) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
  const keys = Reflect.ownKeys(value);
  return keys.length === expected.length &&
    keys.every(key => typeof key === "string" && expected.includes(key)) &&
    expected.every(key => Object.getOwnPropertyDescriptor(value, key)?.value !== undefined &&
      Object.hasOwn(Object.getOwnPropertyDescriptor(value, key), "value"));
}

function canonicalOrigin(origin) {
  if (typeof origin !== "string" || origin.length > 260 ||
      /[\u0000-\u0020\u007f]/u.test(origin)) return false;
  const url = new URL(origin);
  const labels = url.hostname.split(".");
  return url.protocol === "https:" && url.origin + "/" === origin &&
    !url.username && !url.password && !url.port &&
    labels.length >= 2 && url.hostname.length <= 253 &&
    /^[a-z]{2,63}$/u.test(labels.at(-1)) &&
    labels.every(label => label.length <= 63 &&
      /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/u.test(label));
}

function verifiedContext(record, request) {
  if (!exact(record, FIELDS) || own(record, "requestId") !== request.requestId ||
      own(record, "tabId") !== request.tabId ||
      own(record, "frameId") !== request.frameId ||
      own(record, "selectionId") !== request.selectionId ||
      typeof own(record, "resourceId") !== "string" ||
      !ID.test(own(record, "resourceId")) ||
      !canonicalOrigin(own(record, "documentOrigin")) ||
      !canonicalOrigin(own(record, "resourceOrigin")) ||
      own(record, "verified") !== true ||
      own(record, "permissionGranted") !== true) return null;
  return Object.freeze(Object.fromEntries(FIELDS.map(key => [key, own(record, key)])));
}

function identical(a, b) {
  return Boolean(a && b && FIELDS.every(key => a[key] === b[key]));
}

function explicitlyDeclaredTarget(manifest, targetOrigin) {
  if (own(manifest, "manifest_version") !== 3) return false;
  const required = own(manifest, "host_permissions");
  const optional = own(manifest, "optional_host_permissions");
  if (!Array.isArray(required) || required.length !== 0 ||
      !Array.isArray(optional) || optional.length === 0 ||
      optional.length > 32) return false;
  let found = false;
  for (let i = 0; i < optional.length; i++) {
    const pattern = own(optional, String(i));
    if (typeof pattern !== "string" || !pattern.endsWith("*") ||
        !canonicalOrigin(pattern.slice(0, -1))) return false;
    if (pattern === targetOrigin + "*") found = true;
  }
  return found;
}

/**
 * Inspect only a trusted current-PDF request and browser-owned origin context.
 * The coordinator must independently authenticate the document, selected PDF,
 * and final response origin (including every cross-origin redirect).
 *
 * This never requests permissions. For a different HTTPS origin, a future
 * opted-in manifest must declare precisely that host, the browser must confirm
 * its CURRENT grant, and permission removals must be observed during awaits.
 * A verified grant is only a permission status: it does NOT prove that CORS,
 * page authentication, local-file access or native scanner admission succeeds.
 */
export async function assessExplicitPdfCrossOrigin({
  request, coordinator, permissionsApi, manifest
} = {}) {
  let revocations = null;
  try {
    const details = describeExplicitPdfScanRequest(request);
    if (!details || own(coordinator, "crossOriginPdfReady") !== true) return unavailable;
    const read = own(coordinator, "readVerifiedPdfOriginContext");
    if (typeof read !== "function") return unavailable;
    const reference = Object.freeze({
      requestId: details.requestId, tabId: details.tabId,
      frameId: details.frameId, selectionId: details.selectionId
    });
    const before = verifiedContext(read.call(coordinator, reference), details);
    if (!before) return unavailable;
    const current = () => own(coordinator, "crossOriginPdfReady") === true &&
      own(coordinator, "readVerifiedPdfOriginContext") === read &&
      identical(before, verifiedContext(read.call(coordinator, reference), details));

    if (before.documentOrigin === before.resourceOrigin) {
      return current() ? sameOrigin : unavailable;
    }

    // A different subdomain, port, or redirect destination is another origin.
    // No broad host grant, all_urls, or page-provided CORS workaround is valid.
    if (!explicitlyDeclaredTarget(manifest, before.resourceOrigin) ||
        typeof own(permissionsApi, "contains") !== "function") {
      return current() ? restricted : unavailable;
    }

    // Without reliable removal tracking, the effective permission state
    // cannot be trusted across asynchronous checks.
    try {
      revocations = subscribeToPermissionRevocations(permissionsApi, () => {});
    } catch {
      return restricted;
    }
    const contains = own(permissionsApi, "contains");
    const pattern = before.resourceOrigin + "*";
    const grantedNow = async () => {
      const check = contains.call(permissionsApi, { origins: [pattern] });
      return check && typeof check.then === "function" && await check === true;
    };
    if (!await grantedNow() || revocations.isRevoked("siteAccess")) return restricted;
    if (!current()) return unavailable;
    // Recheck grant and current selection after asynchronous browser work.
    if (!await grantedNow() || revocations.isRevoked("siteAccess")) return restricted;
    return current() && !revocations.isRevoked("siteAccess") &&
      own(permissionsApi, "contains") === contains ? granted : unavailable;
  } catch {
    // Unsafe data, revoked access, or browser errors cannot enable a transfer.
    return unavailable;
  } finally {
    try { revocations?.unsubscribe(); } catch { /* never grant on cleanup failure */ }
  }
}
