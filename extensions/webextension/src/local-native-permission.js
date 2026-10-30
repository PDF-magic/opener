// Opt-in WebExtensions permission request for a separately verified *local*
// native integration. This module neither registers a host nor connects to it.
// The inactive shared extension does not declare this optional permission.

const NATIVE_PERMISSION = "nativeMessaging";
const HOST_NAME = /^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$/;

const result = (reason) => Object.freeze({ granted: reason === "granted", reason });

function ownData(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  try {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
  } catch {
    return undefined;
  }
}

function localHostReady(localHost) {
  const name = ownData(localHost, "name");
  return ownData(localHost, "registrationVerified") === true &&
    typeof name === "string" && name.length <= 128 && HOST_NAME.test(name);
}

function declaredForOptionalLocalUse(manifest) {
  const optional = ownData(manifest, "optional_permissions");
  const required = ownData(manifest, "permissions");
  const hostAccess = ownData(manifest, "host_permissions");
  return ownData(manifest, "manifest_version") === 3 &&
    Array.isArray(optional) && optional.length === 1 &&
    ownData(optional, "0") === NATIVE_PERMISSION &&
    Array.isArray(required) && required.length === 0 &&
    Array.isArray(hostAccess) && hostAccess.length === 0 &&
    ownData(manifest, "optional_host_permissions") === undefined;
}

/**
 * Request *only* nativeMessaging for a verified, registered local host, from
 * an explicit user gesture. The caller must independently verify host
 * registration and supply the current browser manifest. A boolean here is
 * not proof of host authenticity, scanner approval, or a native connection.
 *
 * The request() call executes synchronously before returning the Promise,
 * preserving the browser's required direct user-gesture context. Promise APIs
 * are supported (Chromium MV3 and Firefox); unsupported adapters fail closed.
 * The returned status contains no host name, paths or browser error details.
 */
export function requestLocalNativeMessagingPermission({
  permissionsApi, manifest, localHost, userInitiated
} = {}) {
  if (userInitiated !== true || !localHostReady(localHost)) {
    return Promise.resolve(result("local-integration-required"));
  }
  if (!declaredForOptionalLocalUse(manifest)) {
    return Promise.resolve(result("optional-permission-unavailable"));
  }
  const request = ownData(permissionsApi, "request");
  if (typeof request !== "function") {
    return Promise.resolve(result("permission-api-unavailable"));
  }

  // Do not await, schedule a microtask, or inspect a host before this call:
  // browsers require permissions.request to run directly inside a user gesture.
  let response;
  try {
    response = request.call(permissionsApi, { permissions: [NATIVE_PERMISSION] });
    if (response === null || typeof response !== "object" ||
        typeof response.then !== "function") {
      return Promise.resolve(result("permission-api-unavailable"));
    }
  } catch {
    return Promise.resolve(result("permission-request-failed"));
  }
  return Promise.resolve(response).then(
    (granted) => result(granted === true ? "granted" : "denied"),
    () => result("permission-request-failed")
  );
}
