// Shared WebExtensions message envelope. No browser APIs or transport side effects.
export const MESSAGE_VERSION = 1;
export const MAX_MESSAGE_BYTES = 16 * 1024;

const MAX_DEPTH = 8;
const MAX_NODES = 512;
const MAX_ITEMS = 256;
const MAX_STRING = 8192;
const KINDS = new Set(["request", "response", "event"]);
const FIELDS = ["kind", "payload", "requestId", "topic", "version"];
const UNSAFE_KEYS = new Set(["__proto__", "constructor", "prototype"]);

function invalid() {
  throw new TypeError("Invalid shared extension message");
}

function isRecord(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function validateJson(value, depth, budget) {
  budget.count += 1;
  if (budget.count > MAX_NODES || depth > MAX_DEPTH) invalid();

  if (value === null || typeof value === "boolean") return;
  if (typeof value === "string") {
    if (value.length > MAX_STRING) invalid();
    return;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) invalid();
    return;
  }
  if (Array.isArray(value)) {
    if (value.length > MAX_ITEMS || Reflect.ownKeys(value).length !== value.length + 1) {
      invalid();
    }
    for (let i = 0; i < value.length; i += 1) {
      const descriptor = Object.getOwnPropertyDescriptor(value, String(i));
      if (!descriptor || !("value" in descriptor)) invalid();
      validateJson(descriptor.value, depth + 1, budget);
    }
    return;
  }
  if (!isRecord(value)) invalid();
  const keys = Reflect.ownKeys(value);
  if (keys.length > MAX_ITEMS) invalid();
  for (const key of keys) {
    if (typeof key !== "string" || UNSAFE_KEYS.has(key)) invalid();
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor)) invalid();
    validateJson(descriptor.value, depth + 1, budget);
  }
}

function validatedJson(message) {
  if (!isRecord(message)) invalid();
  if (JSON.stringify(Reflect.ownKeys(message).sort()) !== JSON.stringify(FIELDS)) invalid();
  const descriptors = Object.getOwnPropertyDescriptors(message);
  if (FIELDS.some((field) => !("value" in descriptors[field]))) invalid();

  const { version, kind, topic, requestId, payload } = message;
  if (
    version !== MESSAGE_VERSION || !KINDS.has(kind) ||
    typeof topic !== "string" || topic.length > 80 ||
    !/^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)*$/.test(topic) ||
    typeof requestId !== "string" || requestId.length > 80 ||
    !/^[A-Za-z0-9_-]+$/.test(requestId)
  ) invalid();

  validateJson(payload, 0, { count: 0 });
  const json = JSON.stringify(message);
  if (new TextEncoder().encode(json).byteLength > MAX_MESSAGE_BYTES) invalid();
  return json;
}

// Construct a validated, detached message; nothing is sent by this function.
export function createMessage(kind, topic, requestId, payload = null) {
  return JSON.parse(validatedJson({ version: MESSAGE_VERSION, kind, topic, requestId, payload }));
}

// Validate an object delivered by extension message events or a JSON string.
// A detached copy prevents callers from mutating an already-checked payload.
export function parseMessage(value) {
  if (typeof value === "string") {
    if (new TextEncoder().encode(value).byteLength > MAX_MESSAGE_BYTES) invalid();
    try {
      value = JSON.parse(value);
    } catch {
      invalid();
    }
  }
  return JSON.parse(validatedJson(value));
}

export function serializeMessage(value) {
  return validatedJson(value);
}
