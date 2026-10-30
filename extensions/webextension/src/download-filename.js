import { subscribeToPermissionRevocations } from "./permission-revocations.js";

// Completed browser transfers are not scan verdicts or permission to open.
const MAX_FILENAME_LENGTH = 4096;
const own = (value, key) => {
  if (value === null || typeof value !== "object") return undefined;
  const d = Object.getOwnPropertyDescriptor(value, key);
  return d && Object.hasOwn(d, "value") ? d.value : undefined;
};
const method = (value, key) => {
  const d = value && typeof value === "object"
    ? Object.getOwnPropertyDescriptor(value, key) : null;
  return d && Object.hasOwn(d, "value") && typeof d.value === "function"
    ? d.value : null;
};
function completedId(notice) {
  if (notice === null || typeof notice !== "object" || Array.isArray(notice) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(notice)) ||
      Reflect.ownKeys(notice).length !== 2 || own(notice, "kind") !== "completed") return null;
  const id = own(notice, "id");
  return Number.isSafeInteger(id) && id >= 0 ? id : null;
}
function filenameResult(results, id) {
  if (!Array.isArray(results) || results.length !== 1 ||
      !Object.hasOwn(results, "0")) return null;
  const item = own(results, "0");
  if (!item || typeof item !== "object" || Array.isArray(item) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(item)) ||
      own(item, "id") !== id || own(item, "state") !== "complete") return null;
  const filename = own(item, "filename");
  if (typeof filename !== "string" || filename.length === 0 ||
      filename.length > MAX_FILENAME_LENGTH || /[\u0000-\u001f\u007f]/u.test(filename)) return null;
  return Object.freeze({ id, filename });
}

/** One-shot ID-scoped lookup. No import-time activity or automatic permission request. */
export async function retrieveCompletedDownloadFilename(downloadsApi, permissionsApi, completion) {
  let revocations = null;
  try {
    const id = completedId(completion);
    if (id === null) return null;
    const contains = method(permissionsApi, "contains");
    const search = method(downloadsApi, "search");
    if (!contains || !search) return null;
    // Observe permission removal before checking the grant; a late result after
    // revocation must never expose a private local path.
    revocations = subscribeToPermissionRevocations(permissionsApi, () => {});
    const check = contains.call(permissionsApi, { permissions: ["downloads"] });
    if (!check || typeof check.then !== "function" || (await check) !== true ||
        revocations.isRevoked("downloads")) return null;
    const lookup = search.call(downloadsApi, { id });
    if (!lookup || typeof lookup.then !== "function") return null;
    const results = await lookup;
    if (revocations.isRevoked("downloads")) return null;
    return filenameResult(results, id);
  } catch {
    // Browser errors can contain private paths: never echo or log them.
    return null;
  } finally {
    revocations?.unsubscribe();
  }
}
