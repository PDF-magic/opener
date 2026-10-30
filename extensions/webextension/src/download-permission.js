// Consent-gated, optional download permission request (opener-0583).
// This module has no import-time behavior and never registers listeners,
// observes downloads, reads browser globals, scans PDFs or opens applications.
// Call only from a trusted, direct user gesture to enable download monitoring.

const ownMethod = (value, name) => {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return null;
  }
  try {
    const descriptor = Object.getOwnPropertyDescriptor(value, name);
    return descriptor && "value" in descriptor && typeof descriptor.value === "function" ?
      descriptor.value : null;
  } catch {
    return null;
  }
};

/**
 * Ask for the *optional* downloads permission only when a caller explicitly
 * enables download monitoring in direct response to a user action.
 *
 * userInitiated is a caller-provided assertion, NOT proof of a browser
 * gesture; the future UI must invoke this immediately inside its click
 * handler. The request starts synchronously before any await, preserving
 * the browser's transient user activation.
 *
 * Returns true only on an explicit grant. Callback-only, unsupported,
 * rejected and denied implementations all fail closed. No subscription,
 * preference persistence, revocation, native bridge or scanning occurs.
 */
export async function requestDownloadMonitoringPermission(
  permissionsApi,
  { monitoringEnabled = false, userInitiated = false } = {}
) {
  if (monitoringEnabled !== true || userInitiated !== true) return false;

  const request = ownMethod(permissionsApi, "request");
  if (!request) return false;
  try {
    // Hard-coded request; do not accept permission names or origins from
    // downloaded files, user settings or callers. This is never a grant
    // of downloads.open, nativeMessaging, tabs, hosts or scanner authority.
    return (await request.call(permissionsApi, { permissions: ["downloads"] })) === true;
  } catch {
    // Do not reveal browser API errors or infer that access was granted.
    return false;
  }
}
