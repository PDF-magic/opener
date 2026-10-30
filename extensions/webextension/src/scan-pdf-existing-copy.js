import { subscribeToPermissionRevocations } from "./permission-revocations.js";
import { subscribeToDownloadEvents } from "./download-monitoring.js";
import { retrieveCompletedDownloadLocalPath } from "./download-local-path.js";
import { retrieveDownloadSourceUrl } from "./download-source-url.js";
import { preflightCompletedDownloadForScan } from "./download-scan-preflight.js";

// Browser history can suggest a copy; it never proves file identity or safety.
const MAX_URL = 8192;
const MAX_CHANGED = 256;

function own(value, key) {
  if (value === null || typeof value !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ?
    descriptor.value : undefined;
}
function plain(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value) &&
    [Object.prototype, null].includes(Object.getPrototypeOf(value));
}
function sourceUrl(raw) {
  if (typeof raw !== "string" || raw.length === 0 || raw.length > MAX_URL ||
      /[\u0000-\u0020\u007f]/u.test(raw)) return null;
  const url = new URL(raw);
  if (!["https:", "http:"].includes(url.protocol) || !url.hostname ||
      url.username || url.password) return null;
  // Viewer #page fragments never identify the HTTP download.
  url.hash = "";
  return url.href;
}
function selectedSource(selection) {
  if (!plain(selection) || Reflect.ownKeys(selection).length !== 2 ||
      own(selection, "kind") !== "trusted-current-pdf-source" ||
      !Object.hasOwn(selection, "url")) return null;
  return sourceUrl(own(selection, "url"));
}
function matchingId(rows, url) {
  if (!Array.isArray(rows) || rows.length !== 1 ||
      !Object.hasOwn(rows, "0")) return null;
  const item = own(rows, "0");
  if (!plain(item)) return null;
  const id = own(item, "id");
  if (!Number.isSafeInteger(id) || id < 0 ||
      sourceUrl(own(item, "url")) !== url) return null;
  return id;
}

/**
 * Passive, one-shot check for a browser-reported downloaded copy of a
 * separately authenticated current PDF source. A URL or PDF suffix alone
 * is never proof the caller selected/verified the displayed PDF.
 *
 * Returns a privacy-safe, non-authorizing ID candidate or null. Even a
 * browser exists:true claim does not prove local filesystem existence.
 */
export async function findExistingDownloadedPdfCopy(
  downloadsApi, permissionsApi, selection
) {
  let revocations = null;
  let stopEvents = null;
  try {
    const url = selectedSource(selection);
    if (url === null) return null;
    const contains = own(permissionsApi, "contains");
    const search = own(downloadsApi, "search");
    if (typeof contains !== "function" || typeof search !== "function") return null;

    revocations = subscribeToPermissionRevocations(permissionsApi, () => {});
    const changedIds = new Set();
    let invalidated = false;
    stopEvents = subscribeToDownloadEvents(downloadsApi, (event) => {
      if (changedIds.size >= MAX_CHANGED) invalidated = true;
      else changedIds.add(event.id);
    });
    const changed = (id) => invalidated ||
      revocations.isRevoked("downloads") || changedIds.has(id);

    const grant = contains.call(permissionsApi, { permissions: ["downloads"] });
    if (!grant || typeof grant.then !== "function" ||
        (await grant) !== true || revocations.isRevoked("downloads") ||
        invalidated) return null;

    // The browser filter can use regex semantics: escape every metacharacter
    // and still require an exact URL match in the returned record.
    const escaped = url.replace(/[.*+?^$(){}|[\]\\]/gu, "\\$&");
    const request = search.call(downloadsApi, {
      url: "^" + escaped + "$", limit: 16
    });
    if (!request || typeof request.then !== "function") return null;
    const rows = await request;
    if (revocations.isRevoked("downloads") || invalidated) return null;
    const id = matchingId(rows, url);
    if (id === null || changed(id)) return null;

    const completion = Object.freeze({ kind: "completed", id });
    // Each reviewed helper verifies the current grant and exact download ID.
    const local = await retrieveCompletedDownloadLocalPath(
      downloadsApi, permissionsApi, completion
    );
    if (!local || local.id !== id || changed(id)) return null;
    const source = await retrieveDownloadSourceUrl(
      downloadsApi, permissionsApi, completion
    );
    if (!source || source.id !== id || sourceUrl(source.url) !== url ||
        changed(id)) return null;
    // Check browser-reported existence, full byte counts, and no partial
    // transfer LAST; never reuse a path or an earlier completion event.
    const ready = await preflightCompletedDownloadForScan(
      downloadsApi, permissionsApi, completion
    );
    if (!ready || ready.id !== id || ready.transferComplete !== true ||
        ready.scanVerified !== false || ready.authorizesScan !== false ||
        ready.authorizesOpen !== false || changed(id)) return null;

    return Object.freeze({
      kind: "existing-browser-download-candidate",
      downloadId: id, browserReportsExistingCopy: true,
      nativeFileVerified: false, requiresNativeRevalidation: true,
      scanVerified: false, authorizesScan: false, authorizesOpen: false
    });
  } catch {
    // Browser errors and metadata may contain private URLs and local paths.
    return null;
  } finally {
    try { stopEvents?.(); } catch { /* listeners remain untrusted */ }
    try { revocations?.unsubscribe(); } catch { /* fail closed */ }
  }
}
