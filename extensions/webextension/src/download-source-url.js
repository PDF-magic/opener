import { subscribeToPermissionRevocations } from "./permission-revocations.js";

// Source URLs can contain private query tokens. Keep them out of the common
// download event stream, logs, native messages and persisted settings.
const MAX_SOURCE_URL_LENGTH = 8192;
const createdFields = new Set(["kind", "id", "filename", "mime", "state", "danger", "error"]);

function own(value, key) {
  if (value === null || typeof value !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function method(value, key) {
  if (value === null || typeof value !== "object") return null;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") &&
    typeof descriptor.value === "function" ? descriptor.value : null;
}

function downloadNotice(notice) {
  if (notice === null || typeof notice !== "object" || Array.isArray(notice) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(notice))) return null;
  const kind = own(notice, "kind");
  const id = own(notice, "id");
  if (!["created", "completed"].includes(kind) ||
      !Number.isSafeInteger(id) || id < 0) return null;
  const keys = Reflect.ownKeys(notice);
  if (kind === "completed" &&
      (keys.length !== 2 || !keys.every((key) => key === "kind" || key === "id"))) {
    return null;
  }
  if (kind === "created" && (keys.length < 2 ||
      !keys.every((key) => typeof key === "string" && createdFields.has(key)))) {
    return null;
  }
  // A created notice can carry the existing bounded, normalized browser data
  // fields, but never a source URL or arbitrary privileged instructions.
  if (kind === "created") {
    for (const key of keys) {
      if (key === "kind" || key === "id") continue;
      const value = own(notice, key);
      if (typeof value !== "string" || value.length > 4096 ||
          value.includes("\0")) return null;
    }
  }
  return { kind, id };
}

function sourceUrlResult(results, notice) {
  if (!Array.isArray(results) || results.length !== 1 ||
      !Object.hasOwn(results, "0")) return null;
  const item = own(results, "0");
  if (!item || typeof item !== "object" || Array.isArray(item) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(item)) ||
      own(item, "id") !== notice.id) return null;
  const state = own(item, "state");
  if (notice.kind === "completed" ? state !== "complete" :
      state !== "complete" && state !== "in_progress") return null;

  const url = own(item, "url");
  if (typeof url !== "string" || !url.length ||
      url.length > MAX_SOURCE_URL_LENGTH ||
      /[\u0000-\u0020\u007f]/u.test(url)) return null;
  const parsed = new URL(url);
  if (!["https:", "http:"].includes(parsed.protocol) ||
      !parsed.hostname || parsed.username || parsed.password) return null;
  // Return the exact source string, not finalUrl, referrer, filename or any
  // browser safety flag. The trusted caller decides whether it needs the URL.
  return Object.freeze({ id: notice.id, url });
}

/**
 * One-shot source URL retrieval for a sanitized created or completed notice.
 *
 * Call only from trusted, explicitly opted-in extension code. Require a fresh
 * optional downloads permission grant and watch revocation throughout the
 * exact-ID search. Missing, unsafe, ambiguous or stale URLs return null.
 * Never requests access, registers monitoring, downloads content, or opens PDFs.
 */
export async function retrieveDownloadSourceUrl(downloadsApi, permissionsApi, notice) {
  let revocations = null;
  try {
    const expected = downloadNotice(notice);
    if (!expected) return null;
    const contains = method(permissionsApi, "contains");
    const search = method(downloadsApi, "search");
    if (!contains || !search) return null;

    revocations = subscribeToPermissionRevocations(permissionsApi, () => {});
    const check = contains.call(permissionsApi, { permissions: ["downloads"] });
    if (!check || typeof check.then !== "function" || (await check) !== true ||
        revocations.isRevoked("downloads")) return null;

    const request = search.call(downloadsApi, { id: expected.id });
    if (!request || typeof request.then !== "function") return null;
    const results = await request;
    if (revocations.isRevoked("downloads")) return null;
    return sourceUrlResult(results, expected);
  } catch {
    // Browser API errors can contain credentials or private URLs. Do not log.
    return null;
  } finally {
    revocations?.unsubscribe();
  }
}
