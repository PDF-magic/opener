// Dormant, least-privilege WebExtensions site-access contract (opener-0587).
// No site grants are declared by the current extension. This module never
// requests permissions on import, watches browser events, scans or opens PDFs.

const unavailable = Object.freeze({
  status: "unavailable", sitePermissionVerified: false, authorizesOpen: false
});
const denied = Object.freeze({
  status: "denied", sitePermissionVerified: false, authorizesOpen: false
});
const granted = Object.freeze({
  status: "granted", sitePermissionVerified: true, authorizesOpen: false
});

function ownData(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  try {
    const field = Object.getOwnPropertyDescriptor(value, key);
    return field && "value" in field ? field.value : undefined;
  } catch {
    return undefined;
  }
}

// Accept only an exact, canonical HTTPS website origin. No paths, ports,
// IP/local hosts, wildcard subdomains, schemes or implicit URL normalization.
function sitePattern(siteOrigin) {
  if (typeof siteOrigin !== "string" || siteOrigin.length > 260) return null;
  try {
    const url = new URL(siteOrigin);
    const labels = url.hostname.split(".");
    if (url.protocol !== "https:" || url.origin + "/" !== siteOrigin ||
        url.username || url.password || url.port || labels.length < 2 ||
        url.hostname.length > 253 || !/^[a-z]{2,63}$/.test(labels.at(-1)) ||
        !labels.every((label) =>
          label.length <= 63 && /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(label))) {
      return null;
    }
    return `${siteOrigin}*`;
  } catch {
    return null;
  }
}

function declaredExactOptionalHost(manifest, pattern) {
  if (ownData(manifest, "manifest_version") !== 3) return false;
  const required = ownData(manifest, "host_permissions");
  const optional = ownData(manifest, "optional_host_permissions");
  if (!Array.isArray(required) || required.length !== 0 ||
      !Array.isArray(optional) || optional.length === 0 || optional.length > 32) {
    return false;
  }
  let found = false;
  try {
    for (let i = 0; i < optional.length; i += 1) {
      const descriptor = Object.getOwnPropertyDescriptor(optional, String(i));
      if (!descriptor || !("value" in descriptor)) return false;
      const declared = descriptor.value;
      if (typeof declared !== "string" || !declared.endsWith("*") ||
          sitePattern(declared.slice(0, -1)) !== declared) return false;
      if (declared === pattern) found = true;
    }
  } catch {
    return false;
  }
  return found;
}

/**
 * Request one exact HTTPS site's optional host access during a real user
 * action, if a separately reviewed MV3 manifest already lists that origin.
 * Calling this function is not evidence of a user gesture: the caller must
 * invoke it directly in a trusted click handler and obtain explicit consent.
 *
 * Browser support is detected through injected Promise-style permissions
 * request/contains APIs, not through browser names or user agents. Never
 * fall back to required host permissions or broad origin patterns.
 *
 * @returns {Promise<Readonly<{status: string, sitePermissionVerified: boolean,
 *   authorizesOpen: false}>>}
 */
export async function requestOptionalSitePermission(
  permissionsApi,
  manifest,
  { siteOrigin, siteFeatureEnabled = false, userInitiated = false } = {}
) {
  if (siteFeatureEnabled !== true || userInitiated !== true) return unavailable;
  const pattern = sitePattern(siteOrigin);
  if (!pattern || !declaredExactOptionalHost(manifest, pattern)) return unavailable;
  const request = ownData(permissionsApi, "request");
  const contains = ownData(permissionsApi, "contains");
  if (typeof request !== "function" || typeof contains !== "function") {
    return unavailable;
  }
  try {
    // Must invoke permissions.request synchronously before the first await:
    // browsers require the request to originate in the user's action handler.
    const pending = request.call(permissionsApi, { origins: [pattern] });
    if (!pending || typeof pending.then !== "function") return unavailable;
    if (await pending !== true) return denied;
    const check = contains.call(permissionsApi, { origins: [pattern] });
    if (!check || typeof check.then !== "function") return unavailable;
    return await check === true ? granted : denied;
  } catch {
    return unavailable;
  }
}
