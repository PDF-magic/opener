// Opt-in, permission-checked registration for download-created events (opener-0671).
// This module is dormant until a trusted, user-authorized integration calls it.
// No file bytes, URLs, scanner actions, or native messages are accessed.
import { normalizeDownloadEvent } from "./download-monitoring.js";
import { subscribeToPermissionRevocations } from "./permission-revocations.js";

const noOp = () => {};

function method(source, name) {
  try {
    return typeof source?.[name] === "function" ? source[name] : null;
  } catch {
    return null;
  }
}

/**
 * Register one downloads.onCreated listener only after an explicit opt-in and
 * a verified, CURRENT browser downloads grant. A boolean opt-in is not itself
 * permission, nor proof of a user gesture. A UI must obtain consent separately.
 *
 * No permission is requested, and a fresh call is needed after revocation.
 * The callback receives only the immutable normalized allowlisted metadata.
 * A permission removal is latched synchronously before listener teardown.
 *
 * Returns an idempotent stop function, including for denied/absent APIs.
 */
export async function registerDownloadCreatedEvents(
  downloadsApi, permissionsApi, onCreated,
  { monitoringEnabled = false, onError } = {}
) {
  if (monitoringEnabled !== true) return noOp;
  if (typeof onCreated !== "function" ||
      (onError !== undefined && typeof onError !== "function")) {
    throw new TypeError("A download-created callback is required");
  }
  const event = downloadsApi?.onCreated;
  const add = method(event, "addListener");
  const remove = method(event, "removeListener");
  const contains = method(permissionsApi, "contains");
  if (!add || !remove || !contains) return noOp;

  const reportError = () => {
    try { onError?.(new Error("Download-created monitoring callback failed")); }
    catch { /* never forward consumer exceptions or private metadata */ }
  };
  let stopped = false;
  let attached = false;
  let revocations = null;
  const listener = (payload) => {
    if (stopped || !attached) return;
    try {
      const normalized = normalizeDownloadEvent("created", payload);
      if (normalized === null) return;
      const completion = onCreated(normalized);
      if (completion && typeof completion.then === "function") {
        Promise.resolve(completion).catch(reportError);
      }
    } catch {
      reportError();
    }
  };
  const stop = () => {
    if (stopped) return;
    stopped = true;
    if (attached) {
      attached = false;
      try { remove.call(event, listener); } catch { reportError(); }
    }
    revocations?.unsubscribe();
  };

  // Observe removals before checking the existing grant: a removal while the
  // Promise is pending must prevent a stale grant from attaching listeners.
  try {
    revocations = subscribeToPermissionRevocations(permissionsApi, (state) => {
      if (state.downloadsRevoked) stop();
    }, { onError: reportError });
  } catch {
    return noOp; // Cannot safely track permission loss; fail closed.
  }

  try {
    const check = contains.call(permissionsApi, { permissions: ["downloads"] });
    if (!check || typeof check.then !== "function" ||
        (await check) !== true || stopped || revocations.isRevoked("downloads")) {
      stop();
      return stop;
    }
    add.call(event, listener);
    attached = true;
    // Guard against a synchronous removal during addListener().
    if (stopped || revocations.isRevoked("downloads")) {
      try { remove.call(event, listener); } catch { reportError(); }
      attached = false;
      stop();
    }
  } catch {
    stop();
  }
  return stop;
}
