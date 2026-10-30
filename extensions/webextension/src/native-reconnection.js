import {
  isApprovedNativeExtensionIdentity, snapshotApprovedExtensionIds
} from "./native-extension-identity.js";
import { credentialFreeNativeMessage } from "./native-credential-boundary.js";

// Dormant native-transport recovery for a future explicitly approved integration.
// Importing this module never connects, requests permissions, scans or opens files.
const HOST_NAME = "org.pdfmagic.opener";
const RETRY_DELAYS_MS = Object.freeze([250, 500, 1000]);
const HANDSHAKE_TIMEOUT_MS = 5000;
const SAFE_ID = /^[A-Za-z0-9_-]{16,64}$/;
const HANDSHAKE_FIELDS = Object.freeze([
  "status", "protocolVersion", "clientNonce", "scanAvailable",
  "applicationVersion", "activeProtectionProfile"
]);

function createNonce() {
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function matchesHandshake(message, requestId, nonce) {
  if (message === null || typeof message !== "object" || Array.isArray(message) ||
      Object.keys(message).length !== 5 ||
      !["version", "kind", "topic", "requestId", "payload"]
        .every((key) => Object.hasOwn(message, key)) ||
      message.version !== 1 || message.kind !== "response" ||
      message.topic !== "host.handshake" || message.requestId !== requestId) {
    return false;
  }
  const payload = message.payload;
  return payload !== null && typeof payload === "object" &&
    !Array.isArray(payload) &&
    Object.keys(payload).length === HANDSHAKE_FIELDS.length &&
    HANDSHAKE_FIELDS.every((key) => Object.hasOwn(payload, key)) &&
    payload.status === "transport-only" &&
    payload.protocolVersion === 1 && payload.clientNonce === nonce &&
    payload.scanAvailable === false &&
    (payload.applicationVersion === null ||
      (typeof payload.applicationVersion === "string" &&
       /^[A-Za-z0-9.+-]{1,64}$/.test(payload.applicationVersion))) &&
    (payload.activeProtectionProfile === null ||
      payload.activeProtectionProfile === "built-in");
}

/**
 * Create a session-local native reconnect controller. An independently trusted
 * caller must verify host registration, permission, and explicit user approval
 * before start(). The supplied assertions are not themselves authentication.
 * No requests are replayed and only the read-only host handshake is sent.
 *
 * The returned "ready" state means transport readiness ONLY, never a scan
 * verdict or PDF-opening authorization. No persistent consent is stored.
 */
export function createNativeReconnectController({
  connectNative,
  browserKind,
  browserRuntime,
  approvedExtensionIds,
  development = false,
  nonceFactory = createNonce,
  schedule = (callback, delay) => setTimeout(callback, delay),
  cancel = (handle) => clearTimeout(handle),
  onStateChange = () => {}
} = {}) {
  // Capture only reviewed IDs, not a mutable caller-owned allowlist.
  const approvedIds = snapshotApprovedExtensionIds(approvedExtensionIds);
  const identityAllowed = () => approvedIds !== null &&
    isApprovedNativeExtensionIdentity({
      browserKind, browserRuntime, approvedExtensionIds: approvedIds, development
    });
  let active = false;
  let state = "idle";
  let port = null;
  let generation = 0;
  let retryCount = 0;
  let retryTimer = null;
  let handshakeTimer = null;

  function changeState(next) {
    if (state === next) return;
    state = next;
    // Consumer UI errors must not destabilize the connection safety boundary.
    try { onStateChange(next); } catch { /* no untrusted error output */ }
  }

  function clearTimers() {
    if (retryTimer !== null) cancel(retryTimer);
    if (handshakeTimer !== null) cancel(handshakeTimer);
    retryTimer = null;
    handshakeTimer = null;
  }

  function detachPort() {
    const old = port;
    port = null;
    generation += 1; // Supersede callbacks from old processes.
    if (old && typeof old.disconnect === "function") {
      try { old.disconnect(); } catch { /* no diagnostic leak */ }
    }
  }

  function halt(reason) {
    active = false;
    clearTimers();
    detachPort();
    changeState(reason);
  }

  function retry() {
    if (!active) return;
    clearTimers();
    detachPort();
    if (retryCount >= RETRY_DELAYS_MS.length) {
      halt("unavailable");
      return;
    }
    const delay = RETRY_DELAYS_MS[retryCount++];
    changeState("reconnecting");
    if (!active) return;
    retryTimer = schedule(() => {
      retryTimer = null;
      connect();
    }, delay);
  }

  function connect() {
    if (!active) return;
    // Recheck the current browser runtime identity after every disconnect.
    // A revoked or changed identity never initiates another native process.
    if (!identityAllowed()) { halt("unavailable"); return; }
    changeState("connecting");
    if (!active) return;
    const currentGeneration = ++generation;
    let currentPort;
    try {
      // The caller injects a bound browser API; importing this module does not
      // access runtime APIs or install native host manifests.
      currentPort = connectNative(HOST_NAME);
      if (!currentPort || typeof currentPort.postMessage !== "function" ||
          typeof currentPort.disconnect !== "function" ||
          typeof currentPort.onMessage?.addListener !== "function" ||
          typeof currentPort.onDisconnect?.addListener !== "function") {
        throw new Error("native port unavailable");
      }
      port = currentPort;
      const nonce = nonceFactory();
      if (typeof nonce !== "string" || !SAFE_ID.test(nonce)) {
        halt("unavailable");
        return;
      }
      const requestId = `hello_${nonce}`;
      const outbound = credentialFreeNativeMessage({
        version: 1, kind: "request", topic: "host.handshake", requestId,
        payload: { clientNonce: nonce }
      });
      if (!outbound) { halt("unavailable"); return; }
      let confirmed = false;
      const isCurrent = () => active && port === currentPort &&
        generation === currentGeneration;

      currentPort.onMessage.addListener((message) => {
        if (!isCurrent()) return;
        // Do not accept unsolicited data, privileged replies, or a later
        // replayed handshake as proof of connection authenticity.
        let valid = false;
        try { valid = matchesHandshake(message, requestId, nonce); } catch { /* malformed */ }
        if (confirmed || !valid) {
          halt("protocol-error");
          return;
        }
        confirmed = true;
        if (handshakeTimer !== null) cancel(handshakeTimer);
        handshakeTimer = null;
        changeState("ready");
      });
      currentPort.onDisconnect.addListener(() => {
        if (isCurrent()) retry();
      });
      handshakeTimer = schedule(() => {
        if (isCurrent() && !confirmed) retry();
      }, HANDSHAKE_TIMEOUT_MS);
      // Never forward caller-owned browser metadata to the native host.
      currentPort.postMessage(outbound);
    } catch {
      if (active && generation === currentGeneration) retry();
    }
  }

  return Object.freeze({
    start({ registrationVerified, nativePermissionGranted, userApproved } = {}) {
      if (active || registrationVerified !== true ||
          nativePermissionGranted !== true || userApproved !== true ||
          typeof connectNative !== "function" || !identityAllowed()) return false;
      // Fresh opt-in is required after stop or exhaustion; attempts never
      // survive a controller restart or extension-worker shutdown.
      clearTimers();
      retryCount = 0;
      active = true;
      connect();
      return true;
    },
    stop() { halt("stopped"); },
    get state() { return state; }
  });
}
