// Dormant, browser-neutral permission revocation observer (opener-0590).
// This module never requests or restores permission, changes user preferences,
// or authorizes a PDF scan, native connection, or document opening.

const capabilities = Object.freeze(Object.assign(Object.create(null), {
  downloads: "downloadsRevoked",
  nativeMessaging: "nativeMessagingRevoked",
  notifications: "notificationsRevoked",
  storage: "storageRevoked"
}));
const keys = Object.freeze(Object.keys(capabilities));
const MAX_ITEMS = 64;
const MAX_ITEM_LENGTH = 512;

function ownData(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) return undefined;
  try {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
  } catch {
    return undefined;
  }
}

function readList(input) {
  const values = [];
  try {
    if (!Array.isArray(input) || input.length > MAX_ITEMS) return null;
    for (let i = 0; i < input.length; i += 1) {
      const value = ownData(input, String(i));
      if (typeof value !== "string" || value.length < 1 || value.length > MAX_ITEM_LENGTH) {
        return null;
      }
      values.push(value);
    }
  } catch {
    return null;
  }
  return values;
}

/**
 * Reduce a browser permissions.onRemoved event to permission categories.
 * No site origins, browser identifiers, paths or user settings are returned.
 * Malformed events fail closed by revoking all tracked access categories.
 */
export function normalizePermissionRevocation(details) {
  let permissions;
  let origins;
  let invalid = false;
  try {
    const prototype = Object.getPrototypeOf(details);
    if (prototype !== Object.prototype && prototype !== null) invalid = true;
    const permissionField = Object.getOwnPropertyDescriptor(details, "permissions");
    const originField = Object.getOwnPropertyDescriptor(details, "origins");
    if ((!permissionField && !originField) ||
        (permissionField && !Object.hasOwn(permissionField, "value")) ||
        (originField && !Object.hasOwn(originField, "value"))) invalid = true;
    permissions = permissionField?.value;
    origins = originField?.value;
    if (permissionField && !invalid && !Array.isArray(permissions)) invalid = true;
    if (originField && !invalid && !Array.isArray(origins)) invalid = true;
  } catch {
    invalid = true;
  }
  const permissionNames = permissions === undefined ? [] : readList(permissions);
  const originPatterns = origins === undefined ? [] : readList(origins);
  invalid ||= permissionNames === null || originPatterns === null;
  const revoked = Object.fromEntries(Object.values(capabilities).map((key) => [key, invalid]));
  revoked.siteAccessRevoked = invalid || originPatterns?.length > 0;
  if (!invalid) {
    for (const permission of permissionNames) {
      if (Object.hasOwn(capabilities, permission)) revoked[capabilities[permission]] = true;
    }
  }
  return Object.freeze(revoked);
}

function snapshot(blocked) {
  return Object.freeze({ ...blocked, authorizesOpen: false, permissionsVerified: false });
}

/**
 * Subscribe only when a future reviewed integration explicitly calls this.
 * onRevoked must synchronously stop the corresponding download, messaging,
 * notification or site-access operations and cancel in-flight requests.
 * Revocation flags latch until a fresh, separately verified integration is
 * created; onAdded events never silently re-enable a capability.
 *
 * A false revocation flag is NEVER proof a permission is currently granted.
 * Callers must check the effective browser grant before each privileged use.
 */
export function subscribeToPermissionRevocations(permissionsApi, onRevoked, { onError } = {}) {
  const event = ownData(permissionsApi, "onRemoved");
  const add = ownData(event, "addListener");
  const remove = ownData(event, "removeListener");
  if (typeof onRevoked !== "function" ||
      (onError !== undefined && typeof onError !== "function") ||
      typeof add !== "function" || typeof remove !== "function") {
    throw new TypeError("A complete browser permission removal source and teardown callback are required");
  }

  const blocked = Object.fromEntries([
    ...Object.values(capabilities), "siteAccessRevoked"
  ].map((name) => [name, false]));
  let active = false;
  const reportError = () => {
    try { onError?.(new Error("Permission revocation cleanup failed")); } catch { /* isolated */ }
  };
  const listener = (details) => {
    if (!active) return;
    const removed = normalizePermissionRevocation(details);
    let changed = false;
    for (const key of Object.keys(blocked)) {
      if (removed[key] && !blocked[key]) {
        blocked[key] = true; // Disable synchronously before notifying consumers.
        changed = true;
      }
    }
    if (!changed) return; // Ignore unrelated and duplicate revocations.
    try { onRevoked(snapshot(blocked)); } catch { reportError(); }
  };
  try {
    add.call(event, listener);
    active = true;
  } catch {
    try { remove.call(event, listener); } catch { /* best-effort rollback */ }
    throw new TypeError("Permission revocation listener could not be registered");
  }
  return Object.freeze({
    state: () => snapshot(blocked),
    isRevoked: (permission) => {
      if (permission === "siteAccess") return blocked.siteAccessRevoked;
      if (!keys.includes(permission)) return true; // Unknown capability fails closed.
      return blocked[capabilities[permission]];
    },
    unsubscribe: () => {
      if (!active) return;
      active = false;
      try { remove.call(event, listener); } catch { reportError(); }
    }
  });
}
