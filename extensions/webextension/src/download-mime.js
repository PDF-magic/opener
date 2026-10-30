import { subscribeToPermissionRevocations } from "./permission-revocations.js";

// Browser-declared MIME types are untrusted metadata, never content sniffing,
// a malware scan, or permission to open a downloaded file.
const MAX_MIME_LENGTH = 255;
const mimePattern = /^[A-Za-z0-9!#$%&'*+.^_|~-]+\/[A-Za-z0-9!#$%&'*+.^_|~-]+(?: *; *[A-Za-z0-9!#$%&'*+.^_|~-]+ *= *(?:[A-Za-z0-9!#$%&'*+.^_|~-]+|"[^"]*"))*$/;

function own(value, key) {
  if (value === null || typeof value !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function method(value, key) {
  const descriptor = value !== null && typeof value === "object"
    ? Object.getOwnPropertyDescriptor(value, key) : null;
  return descriptor && Object.hasOwn(descriptor, "value") &&
    typeof descriptor.value === "function" ? descriptor.value : null;
}

function completedId(notice) {
  if (notice === null || typeof notice !== "object" || Array.isArray(notice) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(notice)) ||
      Reflect.ownKeys(notice).length !== 2 ||
      own(notice, "kind") !== "completed") return null;
  const id = own(notice, "id");
  return Number.isSafeInteger(id) && id >= 0 ? id : null;
}

function declaredMimeResult(results, id) {
  if (!Array.isArray(results) || results.length !== 1 ||
      !Object.hasOwn(results, "0")) return null;
  const item = own(results, "0");
  if (!item || typeof item !== "object" || Array.isArray(item) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(item)) ||
      own(item, "id") !== id || own(item, "state") !== "complete") return null;
  const mime = own(item, "mime");
  if (typeof mime !== "string" || mime.length < 3 ||
      mime.length > MAX_MIME_LENGTH || !mimePattern.test(mime)) return null;
  // Return only the browser declaration, not filename, URL, danger or bytes.
  return Object.freeze({ id, mime });
}

/**
 * One-shot lookup for a completed download's browser-declared MIME type.
 * Caller must have independently obtained consent. The effective downloads
 * permission is verified anew, with revocation tracked throughout the query.
 * Missing, unsupported, ambiguous and stale results fail closed. This module
 * never requests permissions, examines file bytes or registers listeners on
 * import, and no MIME value can authorize scanning or opening a PDF.
 */
export async function retrieveCompletedDownloadMime(downloadsApi, permissionsApi, completion) {
  let revocations = null;
  try {
    const id = completedId(completion);
    if (id === null) return null;
    const contains = method(permissionsApi, "contains");
    const search = method(downloadsApi, "search");
    if (!contains || !search) return null;

    // Start watching before the grant check; otherwise a removal during an
    // async operation could permit private metadata to escape after revocation.
    revocations = subscribeToPermissionRevocations(permissionsApi, () => {});
    const check = contains.call(permissionsApi, { permissions: ["downloads"] });
    if (!check || typeof check.then !== "function" || (await check) !== true ||
        revocations.isRevoked("downloads")) return null;

    const lookup = search.call(downloadsApi, { id });
    if (!lookup || typeof lookup.then !== "function") return null;
    const results = await lookup;
    if (revocations.isRevoked("downloads")) return null;
    return declaredMimeResult(results, id);
  } catch {
    // Browser API failures may include sensitive data; do not expose them.
    return null;
  } finally {
    revocations?.unsubscribe();
  }
}
