// Fail-closed ingress for future extension-owned, read-only native status requests.
// Not registered with a browser listener. No native access is enabled here.
const fields = ["kind", "payload", "requestId", "topic", "version"];
const safeRequestId = /^[A-Za-z0-9_-]{1,80}$/;
const chromiumId = /^[a-p]{32}$/;
const firefoxId = /^(?:[A-Za-z0-9._+-]{1,64}@[A-Za-z0-9.-]{1,253}|\{[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\})$/;
const firefoxHost = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/;
const readOnlyTopics = new Set(["host.ping", "host.health"]);

function ownData(object, key) {
  const descriptor = Object.getOwnPropertyDescriptor(object, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function plainRecord(object) {
  return object !== null && typeof object === "object" &&
    !Array.isArray(object) &&
    (Object.getPrototypeOf(object) === Object.prototype ||
      Object.getPrototypeOf(object) === null);
}

function trustedBase(extensionId, extensionBaseUrl) {
  if (typeof extensionId !== "string" || typeof extensionBaseUrl !== "string") return null;
  const base = new URL(extensionBaseUrl);
  const chromium = base.protocol === "chrome-extension:" &&
    chromiumId.test(extensionId) && base.hostname === extensionId;
  const firefox = base.protocol === "moz-extension:" &&
    firefoxId.test(extensionId) && firefoxHost.test(base.hostname);
  if ((!chromium && !firefox) || base.username || base.password || base.port ||
      base.pathname !== "/" || base.search || base.hash ||
      extensionBaseUrl !== `${base.protocol}//${base.hostname}/`) return null;
  return { protocol: base.protocol, hostname: base.hostname, extensionId };
}

function safeSender(sender, base) {
  if (!plainRecord(sender) || ownData(sender, "id") !== base.extensionId ||
      Object.hasOwn(sender, "tab") || Object.hasOwn(sender, "frameId")) return false;
  const rawUrl = ownData(sender, "url");
  if (typeof rawUrl !== "string" || rawUrl.length > 2048) return false;
  const source = new URL(rawUrl);
  if (source.protocol !== base.protocol || source.hostname !== base.hostname ||
      source.username || source.password || source.port || !source.pathname.startsWith("/")) {
    return false;
  }
  // If the browser supplied an origin, it must also be the extension origin.
  if (Object.hasOwn(sender, "origin") &&
      ownData(sender, "origin") !== `${base.protocol}//${base.hostname}`) return false;
  return true;
}

function readOnlyRequest(message) {
  if (!plainRecord(message) ||
      JSON.stringify(Reflect.ownKeys(message).sort()) !== JSON.stringify(fields)) return null;
  const version = ownData(message, "version");
  const kind = ownData(message, "kind");
  const topic = ownData(message, "topic");
  const requestId = ownData(message, "requestId");
  const payload = ownData(message, "payload");
  if (version !== 1 || kind !== "request" || !readOnlyTopics.has(topic) ||
      typeof requestId !== "string" || !safeRequestId.test(requestId) ||
      payload !== null) return null;
  return Object.freeze({ version: 1, kind: "request", topic, requestId, payload: null });
}

/**
 * Trusted extension code can wire handleRuntimeMessage ONLY to its own
 * runtime.onMessage listener, passing the browser-provided sender (never page
 * data). Never wire external-message listeners, content scripts or page events.
 * The independently trusted callback must itself enforce permission and host
 * authorization; this gate cannot attest browser process authenticity.
 */
export function createNativePageIngress({
  extensionId, extensionBaseUrl, onReadOnlyRequest
} = {}) {
  let base = null;
  try { base = trustedBase(extensionId, extensionBaseUrl); } catch { /* deny */ }
  return Object.freeze({
    handleRuntimeMessage(message, sender) {
      if (!base || typeof onReadOnlyRequest !== "function") return false;
      try {
        if (!safeSender(sender, base)) return false;
        const safe = readOnlyRequest(message);
        if (!safe) return false;
        onReadOnlyRequest(safe);
        return true;
      } catch {
        return false;
      }
    }
  });
}
