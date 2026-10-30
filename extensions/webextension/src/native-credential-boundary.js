// Credential-free outgoing native messaging boundary.
// Only the approved transport handshake is permitted. Never pass raw browser
// events, cookies, authorization headers, URLs or settings to a native port.
const ENVELOPE_FIELDS = ["kind", "payload", "requestId", "topic", "version"];
const PAYLOAD_FIELDS = ["clientNonce"];
const CHALLENGE = /^[A-Za-z0-9_-]{16,64}$/;

function exactlyOwnData(object, fields) {
  if (object === null || typeof object !== "object" || Array.isArray(object)) {
    return false;
  }
  const prototype = Object.getPrototypeOf(object);
  if (prototype !== Object.prototype && prototype !== null) return false;
  const keys = Reflect.ownKeys(object);
  return keys.length === fields.length && fields.every((field) => {
    const descriptor = Object.getOwnPropertyDescriptor(object, field);
    return descriptor !== undefined && Object.hasOwn(descriptor, "value");
  });
}

/**
 * Take an untrusted proposed outbound message and build a fresh, detached
 * allowlisted transport-only request. This function cannot send messages or
 * collect browser data. Any extra field, including credential-bearing fields
 * or a different topic, fails closed instead of being silently stripped.
 *
 * A trusted connector must obtain the challenge from Web Crypto; syntactic
 * validation cannot determine whether an arbitrary string is a credential.
 */
export function credentialFreeNativeMessage(proposed) {
  try {
    if (!exactlyOwnData(proposed, ENVELOPE_FIELDS)) return null;
    const version = Object.getOwnPropertyDescriptor(proposed, "version").value;
    const kind = Object.getOwnPropertyDescriptor(proposed, "kind").value;
    const topic = Object.getOwnPropertyDescriptor(proposed, "topic").value;
    const requestId = Object.getOwnPropertyDescriptor(proposed, "requestId").value;
    const payload = Object.getOwnPropertyDescriptor(proposed, "payload").value;
    if (version !== 1 || kind !== "request" || topic !== "host.handshake" ||
        !exactlyOwnData(payload, PAYLOAD_FIELDS)) return null;
    const clientNonce = Object.getOwnPropertyDescriptor(payload, "clientNonce").value;
    if (typeof clientNonce !== "string" || !CHALLENGE.test(clientNonce) ||
        requestId !== `hello_${clientNonce}`) return null;
    return Object.freeze({
      version: 1, kind: "request", topic: "host.handshake", requestId,
      payload: Object.freeze({ clientNonce })
    });
  } catch {
    // Never reveal a rejected browser field or credential in diagnostics.
    return null;
  }
}
