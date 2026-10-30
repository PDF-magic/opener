import { subscribeToPermissionRevocations } from "./permission-revocations.js";
import { subscribeToDownloadEvents } from "./download-monitoring.js";

// A download can finish transferring before post-download monitoring or
// scanning finishes. Browser completion is not scanner authorization, and
// the ordinary downloads permission cannot guarantee that browser/OS
// opening is blocked. This is a passive, snapshot-based risk assessment.
const responses = Object.freeze({
  unknown: Object.freeze({
    status: "unknown", browserMayOpenBeforeMonitoringCompletes: null,
    openingBlocked: false, scanVerified: false, authorizesOpen: false
  }),
  possible: Object.freeze({
    status: "opening-possible", browserMayOpenBeforeMonitoringCompletes: true,
    openingBlocked: false, scanVerified: false, authorizesOpen: false
  }),
  transferring: Object.freeze({
    status: "transfer-in-progress", browserMayOpenBeforeMonitoringCompletes: null,
    openingBlocked: false, scanVerified: false, authorizesOpen: false
  }),
  interrupted: Object.freeze({
    status: "transfer-interrupted", browserMayOpenBeforeMonitoringCompletes: null,
    openingBlocked: false, scanVerified: false, authorizesOpen: false
  })
});

function own(value, key) {
  if (value === null || typeof value !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function ownMethod(value, key) {
  const method = own(value, key);
  return typeof method === "function" ? method : null;
}

function pendingId(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value)) ||
      Reflect.ownKeys(value).length !== 2 ||
      own(value, "kind") !== "monitoring-pending") return null;
  const id = own(value, "id");
  return Number.isSafeInteger(id) && id >= 0 ? id : null;
}

function assessResult(rows, id) {
  if (!Array.isArray(rows) || rows.length !== 1 ||
      !Object.hasOwn(rows, "0")) return responses.unknown;
  const item = own(rows, "0");
  if (item === null || typeof item !== "object" || Array.isArray(item) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(item)) ||
      own(item, "id") !== id) return responses.unknown;

  const state = own(item, "state");
  if (state === "in_progress") return responses.transferring;
  if (state === "interrupted") return responses.interrupted;
  if (state !== "complete") return responses.unknown;

  // Completion makes browser or external opening a *possibility*, not a
  // promise or proof it happened. Browser danger labels cannot certify
  // safety or prove the browser blocks opening. Recheck current existence
  // rather than trusting an older onChanged event.
  return own(item, "exists") === true &&
    own(item, "paused") === false &&
    own(item, "canResume") === false &&
    own(item, "error") === undefined
    ? responses.possible : responses.unknown;
}

/**
 * Assess whether a browser download could be opened while trusted native
 * monitoring is still pending. The input is only a locally owned
 * {kind:"monitoring-pending", id} notice; it cannot be constructed from
 * arbitrary page content. Requery that exact download with current optional
 * downloads permission, observing revocation and ID mutations during await.
 *
 * A completed, existing item yields "opening-possible": the browser or OS
 * might allow opening independent of the extension's pending scanner.
 * In-progress and interrupted items are *not* declared blocked: external
 * opening and changing browser state cannot be ruled out from this API.
 * This function never opens, pauses, cancels, removes or manipulates a file.
 *
 * Production enforcement requires an independently trusted native
 * coordinator and possibly browser/OS policy outside WebExtensions.
 */
export async function assessDownloadOpeningBeforeMonitoringCompletes(
  downloadsApi, permissionsApi, pending
) {
  let revocations = null;
  let stopEvents = null;
  try {
    const id = pendingId(pending);
    if (id === null) return responses.unknown;
    const contains = ownMethod(permissionsApi, "contains");
    const search = ownMethod(downloadsApi, "search");
    if (!contains || !search) return responses.unknown;

    revocations = subscribeToPermissionRevocations(permissionsApi, () => {});
    let invalidated = false;
    stopEvents = subscribeToDownloadEvents(downloadsApi, (event) => {
      if (event.id === id && (event.kind === "erased" ||
          event.kind === "created" || event.kind === "changed")) {
        invalidated = true;
      }
    });
    const changed = () => invalidated || revocations.isRevoked("downloads");

    const grant = contains.call(permissionsApi, { permissions: ["downloads"] });
    if (!grant || typeof grant.then !== "function" ||
        (await grant) !== true || changed()) return responses.unknown;

    const lookup = search.call(downloadsApi, { id });
    if (!lookup || typeof lookup.then !== "function") return responses.unknown;
    const rows = await lookup;
    if (changed()) return responses.unknown;
    return assessResult(rows, id);
  } catch {
    // Browser API failures can contain URLs or local paths; never log them.
    return responses.unknown;
  } finally {
    try { stopEvents?.(); } catch { /* listeners remain disabled */ }
    try { revocations?.unsubscribe(); } catch { /* fail closed */ }
  }
}
