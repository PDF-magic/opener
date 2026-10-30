/**
 * Conservative WebExtensions capability flags (opener-0573).
 *
 * Only inspect an explicitly supplied extension API namespace, never global
 * browser objects or user-agent strings. API presence is not permission,
 * authorization, a scanner verdict, or evidence of an installed integration.
 */

export const BROWSER_CAPABILITY_NAMES = Object.freeze([
  "runtimeMetadataApi",
  "runtimeMessagingApi",
  "downloadEventsApi",
  "nativeMessagingEnabled",
  "pdfOpeningEnabled",
  "scannerVerificationEnabled"
]);

// Descriptors avoid executing untrusted getters during feature detection.
// Unknown or inherited API members are treated as unavailable (fail closed).
function ownData(object, key) {
  if (object === null || (typeof object !== "object" && typeof object !== "function")) {
    return undefined;
  }
  try {
    const descriptor = Object.getOwnPropertyDescriptor(object, key);
    return descriptor && "value" in descriptor ? descriptor.value : undefined;
  } catch {
    return undefined;
  }
}

const hasMethod = (object, name) => typeof ownData(object, name) === "function";

function hasListenerApi(event) {
  return hasMethod(event, "addListener") && hasMethod(event, "removeListener");
}

/**
 * Detect *API shapes*, not effective permissions, for an explicitly selected
 * browser/chrome extension namespace. The caller is responsible for selecting
 * its namespace, checking effective permissions and authorizing operations.
 *
 * Importing or calling this function never registers listeners, requests
 * permissions, sends messages, reads documents or invokes extension APIs.
 *
 * @param {{runtime?: object, downloads?: object}} api
 * @returns {Readonly<Record<string, boolean>>}
 */
export function getBrowserCapabilityFlags(api = {}) {
  const runtime = ownData(api, "runtime");
  const downloads = ownData(api, "downloads");
  const flags = {
    runtimeMetadataApi: hasMethod(runtime, "getManifest") && hasMethod(runtime, "getURL"),
    runtimeMessagingApi: hasMethod(runtime, "sendMessage") &&
      hasListenerApi(ownData(runtime, "onMessage")),
    downloadEventsApi: ["onCreated", "onChanged", "onErased"].every(
      (name) => hasListenerApi(ownData(downloads, name))
    ),
    // No native host, PDF-open route or scanner bridge is implemented here.
    nativeMessagingEnabled: false,
    pdfOpeningEnabled: false,
    scannerVerificationEnabled: false
  };
  return Object.freeze(flags);
}
