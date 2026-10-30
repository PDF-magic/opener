import { retrieveCompletedDownloadLocalPath } from "./download-local-path.js";
import { preflightCompletedDownloadForScan } from "./download-scan-preflight.js";

// Browser paths are untrusted, even after a successful completed-download
// lookup. Never use a previous path as a fallback for a moved/missing file.
function own(value, key) {
  if (!value || typeof value !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function priorLocation(previous) {
  if (!previous || typeof previous !== "object" || Array.isArray(previous) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(previous)) ||
      Reflect.ownKeys(previous).length !== 2) return null;
  const id = own(previous, "id");
  const path = own(previous, "localPath");
  if (!Number.isSafeInteger(id) || id < 0 ||
      typeof path !== "string" || path.length < 2 || path.length > 4096 ||
      /[\u0000-\u001f\u007f]/u.test(path)) return null;
  // Previously resolved paths must be local, absolute, and unambiguous.
  const windows = /^[A-Za-z]:[/\\]/u.test(path);
  const posix = path.startsWith("/") && !path.startsWith("//");
  if (!windows && !posix) return null;
  if (windows && path.slice(2).includes(":")) return null;
  const parts = windows ? path.slice(3).split(/[/\\]/u) : path.slice(1).split("/");
  if (!parts.length || parts.some(part => !part || part === "." || part === "..")) {
    return null;
  }
  return { id, path };
}

function completedId(completion) {
  if (!completion || typeof completion !== "object" || Array.isArray(completion) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(completion)) ||
      Reflect.ownKeys(completion).length !== 2 ||
      own(completion, "kind") !== "completed") return null;
  const id = own(completion, "id");
  return Number.isSafeInteger(id) && id >= 0 ? id : null;
}

/**
 * Reconcile the browser-reported location immediately before any future
 * native scan dispatch. Never reuse an old path after a missing or changed
 * download record. Reuse the reviewed exact-ID permission-checked lookup,
 * including permission-revocation handling.
 *
 * This DOES NOT verify a file on disk, detect moves unreported by the browser,
 * or authorize scanning/opening. A trusted native coordinator must still
 * establish canonical file identity and stability at dispatch time.
 */
export async function recheckCompletedDownloadLocation(
  downloadsApi, permissionsApi, completion, previous
) {
  try {
    const id = completedId(completion);
    const prior = priorLocation(previous);
    if (id === null || !prior || prior.id !== id) return null;

    const current = await retrieveCompletedDownloadLocalPath(
      downloadsApi, permissionsApi, completion
    );
    if (!current || current.id !== id) return null;

    // A moved/deleted download may still have a cached browser filename.
    // The separate completed-transfer gate must independently report that
    // this same download ID still exists and is no longer being written.
    // Both queries remain passive; the eventual native scan MUST still
    // revalidate the actual file's canonical identity and stability.
    const readiness = await preflightCompletedDownloadForScan(
      downloadsApi, permissionsApi, completion
    );
    if (!readiness || readiness.id !== id || !readiness.transferComplete) return null;

    return Object.freeze({
      id,
      currentLocalPath: current.localPath,
      browserPathChanged: current.localPath !== prior.path,
      requiresNativeRevalidation: true,
      authorizesScan: false,
      authorizesOpen: false
    });
  } catch {
    // Private browser and filesystem locations are never logged.
    return null;
  }
}
