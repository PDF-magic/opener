import { subscribeToPermissionRevocations } from "./permission-revocations.js";

// Browser-reported completion is necessary before a download can be considered
// for scanning, but never proves file stability, scan success or safe opening.
const MAX_FILENAME_LENGTH = 4096;
const partialSuffix = /\.(?:crdownload|part|partial|download|tmp|icloud)$/iu;

function own(value, key) {
  if (value === null || typeof value !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function ownMethod(value, key) {
  const method = own(value, key);
  return typeof method === "function" ? method : null;
}

function completedId(completion) {
  if (!completion || typeof completion !== "object" || Array.isArray(completion) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(completion)) ||
      Reflect.ownKeys(completion).length !== 2 ||
      own(completion, "kind") !== "completed") return null;
  const id = own(completion, "id");
  return Number.isSafeInteger(id) && id >= 0 ? id : null;
}

function completedTransfer(results, id) {
  if (!Array.isArray(results) || results.length !== 1 ||
      !Object.hasOwn(results, "0")) return false;
  const item = own(results, "0");
  if (!item || typeof item !== "object" || Array.isArray(item) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(item)) ||
      own(item, "id") !== id || own(item, "state") !== "complete") return false;

  // Refuse paused/resumable, deleted, interrupted, or temporarily named
  // transfers even if their browser state is inconsistent.
  if (own(item, "paused") !== false || own(item, "canResume") !== false ||
      own(item, "exists") !== true || own(item, "error") !== undefined) return false;
  const filename = own(item, "filename");
  if (typeof filename !== "string" || filename.length === 0 ||
      filename.length > MAX_FILENAME_LENGTH ||
      /[\u0000-\u001f\u007f]/u.test(filename) ||
      partialSuffix.test(filename) ||
      /^[A-Za-z][A-Za-z0-9+.-]*:\/\//u.test(filename)) return false;

  // The browser should report completed transfer counters, not merely a
  // filename or a possibly stale 'complete' state. -1 is unknown total size.
  const received = own(item, "bytesReceived");
  const total = own(item, "totalBytes");
  if (!Number.isSafeInteger(received) || received <= 0 ||
      !Number.isSafeInteger(total) || total < -1 ||
      (total !== -1 && (total <= 0 || received !== total))) return false;
  return true;
}

/**
 * Passive, one-shot prerequisite for an eventual download-to-scan workflow.
 * Accept only the ID-only completion event from the explicit download event
 * adapter. Recheck that exact item and current downloads permission; refuse
 * ambiguous, incomplete and still-writing transfer metadata. Never request
 * permissions, scan/open a file, or forward its path or bytes.
 *
 * Returning a completed transfer is NOT authorization to scan: a trusted
 * future native coordinator must separately revalidate canonical file
 * identity and stability immediately before dispatch and keep the mandatory
 * ClamAV verification, integrity, quarantine and opening gates.
 */
export async function preflightCompletedDownloadForScan(downloadsApi, permissionsApi, completion) {
  let revocations = null;
  try {
    const id = completedId(completion);
    if (id === null) return null;
    const contains = ownMethod(permissionsApi, "contains");
    const search = ownMethod(downloadsApi, "search");
    if (!contains || !search) return null;

    // A revoked grant must not be resurrected by a late permission check or
    // browser search result.
    revocations = subscribeToPermissionRevocations(permissionsApi, () => {});
    const grant = contains.call(permissionsApi, { permissions: ["downloads"] });
    if (!grant || typeof grant.then !== "function" ||
        (await grant) !== true || revocations.isRevoked("downloads")) return null;

    const lookup = search.call(downloadsApi, { id });
    if (!lookup || typeof lookup.then !== "function") return null;
    const result = await lookup;
    if (revocations.isRevoked("downloads") || !completedTransfer(result, id)) return null;

    return Object.freeze({
      id, transferComplete: true, scanVerified: false,
      authorizesScan: false, authorizesOpen: false
    });
  } catch {
    // Browser errors can contain private local paths: never log or surface.
    return null;
  } finally {
    revocations?.unsubscribe();
  }
}
