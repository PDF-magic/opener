import { subscribeToPermissionRevocations } from "./permission-revocations.js";

// Browser-owned malware warnings are a separate, higher-priority safety gate.
// Never call downloads.acceptDanger, cancel, open, removeFile or erase.
const BROWSER_UNWARNED_STATES = Object.freeze(["safe", "deepScannedSafe"]);

function own(value, key) {
  if (value === null || typeof value !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function method(value, key) {
  const member = own(value, key);
  return typeof member === "function" ? member : null;
}

function completedId(completion) {
  if (completion === null || typeof completion !== "object" ||
      Array.isArray(completion) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(completion)) ||
      Reflect.ownKeys(completion).length !== 2 ||
      own(completion, "kind") !== "completed") return null;
  const id = own(completion, "id");
  return Number.isSafeInteger(id) && id >= 0 ? id : null;
}

function safeBrowserStatus(results, id) {
  if (!Array.isArray(results) || results.length !== 1 ||
      !Object.hasOwn(results, "0") ||
      Reflect.ownKeys(results).length !== 2) return null;
  const item = own(results, "0");
  if (!item || typeof item !== "object" || Array.isArray(item) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(item)) ||
      own(item, "id") !== id || own(item, "state") !== "complete" ||
      own(item, "exists") !== true) return null;
  const danger = own(item, "danger");
  if (!BROWSER_UNWARNED_STATES.includes(danger)) return null;
  return Object.freeze({
    id, browserDanger: danger, authorizesScan: false, authorizesOpen: false
  });
}

/**
 * Passive, one-shot veto before sending a completed download candidate to an
 * independently authenticated native coordinator. A browser warning is NEVER
 * dismissed or treated as a scanner verdict. Only an explicitly un-warned
 * browser status can pass; "accepted" (user bypassed a warning), unknown,
 * absent or changing status fails closed. Browsers without a trustworthy
 * danger field require their own separately reviewed integration.
 *
 * Requires fresh downloads permission and an exact-ID current browser lookup.
 * The returned observation does not authorize a scan or file opening.
 */
export async function verifyBrowserNativeMalwareWarning(
  downloadsApi, permissionsApi, completion
) {
  let revocations = null;
  try {
    const id = completedId(completion);
    if (id === null) return null;
    const contains = method(permissionsApi, "contains");
    const search = method(downloadsApi, "search");
    if (!contains || !search) return null;
    revocations = subscribeToPermissionRevocations(permissionsApi, () => {});
    const grant = contains.call(permissionsApi, { permissions: ["downloads"] });
    if (!grant || typeof grant.then !== "function" ||
        (await grant) !== true || revocations.isRevoked("downloads")) return null;
    const query = search.call(downloadsApi, { id });
    if (!query || typeof query.then !== "function") return null;
    const result = await query;
    if (revocations.isRevoked("downloads")) return null;
    return safeBrowserStatus(result, id);
  } catch {
    // Browser warnings, paths and diagnostics never leak into error output.
    return null;
  } finally {
    revocations?.unsubscribe();
  }
}
