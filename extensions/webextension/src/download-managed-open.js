// An opt-in managed download -> native scan -> verified opening request.
// This is a user-intent interface, NOT a browser interception mechanism.
// A separately authenticated native coordinator owns the URL, download,
// scanner verdict, file identity, quarantine and final application handoff.
export const MANAGED_DOWNLOAD_LABEL = "Download, Scan & Open with PDF Magic";

const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const MAX_REQUESTS = 256;
const HELP = "PDF Magic manages this requested download, scans it, and opens it only after native safety checks pass. Other browser and system opening paths are not blocked.";
const PENDING = "Managed request submitted; awaiting the native coordinator.";
const ACCEPTED = "Managed request queued. Downloading, scanning and opening still require native approval.";
const REJECTED = "Managed workflow unavailable. No successful scan or opening has been confirmed.";

const result = Object.freeze({
  unavailable: Object.freeze({
    status: "unavailable", enabled: false, downloadVerified: false,
    scanVerified: false, authorizesOpen: false, opened: false
  }),
  offered: Object.freeze({
    status: "offered", enabled: true, downloadVerified: false,
    scanVerified: false, authorizesOpen: false, opened: false
  }),
  pending: Object.freeze({
    status: "pending", enabled: false, downloadVerified: false,
    scanVerified: false, authorizesOpen: false, opened: false
  }),
  queued: Object.freeze({
    status: "request-submitted", enabled: false, downloadVerified: false,
    scanVerified: false, authorizesOpen: false, opened: false
  })
});

function own(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function validId(value) {
  return typeof value === "string" && ID.test(value);
}

function exactAcknowledgement(value, managedRequestId) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
  const keys = Reflect.ownKeys(value);
  return keys.length === 2 && keys.includes("accepted") &&
    keys.includes("managedRequestId") &&
    own(value, "managedRequestId") === managedRequestId &&
    own(value, "accepted") === true;
}

/**
 * A single deduplication gate shared across ALL views for one authenticated
 * native session. A rejected, timed-out, or ambiguous attempt still consumes
 * its ID; blindly retrying could download or open the same PDF twice.
 * Disposal invalidates replies but NEVER cancels an already accepted job.
 */
export function createManagedDownloadAndOpenGate() {
  const reserved = new Set();
  let active = true;

  async function requestOnce(managedRequestId, requestManagedOperation) {
    if (!active || !validId(managedRequestId) ||
        typeof requestManagedOperation !== "function") return result.unavailable;
    if (reserved.has(managedRequestId)) return result.unavailable;
    if (reserved.size >= MAX_REQUESTS) return result.unavailable;
    reserved.add(managedRequestId); // Atomic reservation before native handoff.
    try {
      const response = requestManagedOperation(
        Object.freeze({ managedRequestId })
      );
      if (!response || typeof response.then !== "function") return result.unavailable;
      const acknowledgement = await response;
      return active && exactAcknowledgement(acknowledgement, managedRequestId)
        ? result.queued : result.unavailable;
    } catch {
      // Do not expose arbitrary native errors, local paths or resource URLs.
      return result.unavailable;
    }
  }

  function isReserved(managedRequestId) {
    return !active || !validId(managedRequestId) ||
      reserved.has(managedRequestId) || reserved.size >= MAX_REQUESTS;
  }

  function dispose() {
    active = false;
    reserved.clear();
  }
  return Object.freeze({ requestOnce, isReserved, dispose });
}

function validRoot(root) {
  try {
    return root?.nodeType === 1 &&
      typeof root.ownerDocument?.createElement === "function" &&
      typeof root.replaceChildren === "function";
  } catch {
    return false;
  }
}

/**
 * The injected native coordinator must separately authenticate the extension
 * and native host; verify browser eligibility, consent and the user-selected
 * resource; securely acquire the complete PDF itself; enforce live ClamAV
 * freshness, byte/identity integrity, quarantine and selected-app preference;
 * and open it ONLY after all gates pass.
 *
 * managedWorkflowRequired indicates a separately verified browser policy,
 * not a browser/page-provided user-agent string. nativeManagedWorkflowReady
 * is a readiness flag, NOT an authentication credential. The coordinator
 * resolves the opaque ID to its OWN previously consented resource record.
 *
 * No browser download API, native messaging, navigation, permission request,
 * scanner or filesystem operation is initiated by this module.
 */
export function createManagedDownloadAndOpenAction(root, coordinator, gate) {
  if (!validRoot(root)) throw new TypeError("An extension-owned UI element is required");
  let active = true;
  let generation = 0;
  let button = null;
  let clickListener = null;
  let status = result.unavailable;

  function available() {
    return own(coordinator, "managedWorkflowRequired") === true &&
      own(coordinator, "nativeManagedWorkflowReady") === true &&
      typeof own(coordinator, "requestManagedDownloadAndOpen") === "function" &&
      typeof own(gate, "requestOnce") === "function" &&
      typeof own(gate, "isReserved") === "function";
  }

  function hide() {
    if (button && clickListener) button.removeEventListener("click", clickListener);
    button = null;
    clickListener = null;
    root.replaceChildren();
    root.hidden = true;
  }

  function clear() {
    generation += 1;
    hide();
    status = result.unavailable;
  }

  function offer(managedRequestId) {
    clear();
    if (!active) return status;
    try {
      if (!validId(managedRequestId) || !available() ||
          gate.isReserved(managedRequestId)) return status;

      const ticket = generation;
      const action = root.ownerDocument.createElement("button");
      action.type = "button";
      action.textContent = MANAGED_DOWNLOAD_LABEL;
      const explanation = root.ownerDocument.createElement("p");
      explanation.textContent = HELP;
      explanation.setAttribute("role", "status");
      explanation.setAttribute("aria-live", "polite");

      async function onClick(event) {
        if (event?.isTrusted !== true || !active || ticket !== generation ||
            action.disabled || status !== result.offered) return;

        action.disabled = true;
        status = result.pending;
        explanation.textContent = PENDING;
        try {
          if (!available()) throw new Error("Native integration unavailable");
          const send = own(coordinator, "requestManagedDownloadAndOpen");
          // Gate reserves ID before the callback issues the single native
          // command. Only an opaque ID crosses this presentation boundary.
          const outcome = await gate.requestOnce(managedRequestId, (request) =>
            send.call(coordinator, request)
          );
          if (!active || ticket !== generation) return;
          if (!available() || outcome !== result.queued) {
            status = result.unavailable;
            explanation.textContent = REJECTED;
            return;
          }
          // Queued is NOT a downloaded PDF, clean scan, or completed open.
          status = result.queued;
          explanation.textContent = ACCEPTED;
        } catch {
          if (!active || ticket !== generation) return;
          status = result.unavailable;
          explanation.textContent = REJECTED;
        }
      }

      button = action;
      clickListener = onClick;
      action.addEventListener("click", onClick);
      root.replaceChildren(action, explanation);
      root.hidden = false;
      status = result.offered;
    } catch {
      clear();
    }
    return status;
  }

  function state() { return status; }

  function dispose() {
    if (!active) return;
    active = false;
    clear();
  }

  clear();
  return Object.freeze({ offer, state, clear, dispose });
}
