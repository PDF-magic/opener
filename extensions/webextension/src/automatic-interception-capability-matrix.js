import { getBrowserCapabilityFlags } from "./browser-capabilities.js";

// Deployment-oriented matrix for OPTIONAL automatic PDF interception.
// Browser-vendor API documentation is not evidence that an installed browser
// or PDF Magic Opener can intercept a PDF before opening. Research is tracked
// separately in docs/browser-interception-apis.md (opener-0716) and #534.
export const AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX_VERSION = 1;

const entries = [
  ["brave", "Brave", "chromium", "conditional", "conditional-policy", "unverified", "conditional"],
  ["chrome", "Google Chrome", "chromium", "documented", "policy-installed-only", "unverified", "documented"],
  ["chromium", "Chromium", "chromium", "conditional", "conditional-policy", "unverified", "conditional"],
  ["edge", "Microsoft Edge", "chromium", "documented", "policy-installed-only", "unverified", "documented"],
  ["vivaldi", "Vivaldi", "chromium", "conditional", "conditional-policy", "unverified", "conditional"],
  ["opera", "Opera", "chromium", "conditional", "conditional-policy", "unverified", "conditional"],
  ["arc", "Arc", "chromium", "conditional", "conditional-policy", "unverified", "conditional"],
  ["firefox", "Mozilla Firefox", "gecko", "documented", "documented-with-grants", "firefox-only-with-grants", "documented"],
  ["safari", "Apple Safari", "webkit", "safari-specific", "unverified", "unverified", "unverified"]
];

export const AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX = Object.freeze(
  entries.map(([id, name, family, declarativeRules, blockingWebRequest,
    responseFilter, downloadEvents]) => Object.freeze({
    id, name, family, declarativeRules, blockingWebRequest,
    responseFilter, downloadEvents,
    deployment: "inactive",
    permissionState: "not-verified",
    liveBrowserTested: false,
    allPdfOpeningBlocked: false,
    nativeScanInterlockVerified: false
  }))
);


// Explicit deny-by-default decision for browsers and PDF entry paths whose
// native scan-before-render hold cannot be demonstrated in this installation.
// A recorded user preference or observed API shape is never permission to
// intercept. This is an inactive policy decision, NOT a capability probe.
export const AUTOMATIC_INTERCEPTION_RELIABILITY_POLICY_VERSION = 1;
export const AUTOMATIC_INTERCEPTION_PDF_PATHS = Object.freeze([
  "network-main-frame", "inline-browser-viewer", "embedded-pdf",
  "pdfjs-page", "redirected-response", "blob-url", "data-url",
  "file-url", "cached-pdf", "attachment-download"
]);

function disabledReliability(browserId, reason) {
  return Object.freeze({
    status: "disabled-unreliable",
    browserId, reason,
    automaticInterceptionDisabled: true,
    automaticInterceptionEnabled: false,
    blockingPointVerified: false,
    nativeScanInterlockVerified: false,
    allPdfOpeningPathsBlocked: false,
    authorizesScan: false,
    authorizesOpen: false
  });
}

/**
 * Fail closed for every currently unverified browser and PDF route.
 *
 * This guards the distinction between a possible vendor API and a reliable,
 * working native PDF scan-before-render interlock. Even Firefox's documented
 * response filter is not implemented or verified in this extension. Chromium
 * MV3 blocking is enterprise-policy-only; Safari and forks need version-
 * specific validation. A URL or browser viewer path can bypass any matching
 * network request hook. Do not consult stored opt-in flags as proof.
 *
 * A future independently audited integration must separately validate
 * effective permissions, original browser/response identity, complete bytes,
 * native scan/authentication, cleanup, and actual browser-specific release
 * before replacing this permanently disabled decision.
 */
export function assessAutomaticInterceptionReliability(
  browserId, pdfPath = "network-main-frame"
) {
  if (typeof browserId !== "string") {
    return disabledReliability(null, "unsupported-browser");
  }
  const row = AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX.find(
    item => item.id === browserId
  );
  if (!row) return disabledReliability(null, "unsupported-browser");
  if (typeof pdfPath !== "string" ||
      !AUTOMATIC_INTERCEPTION_PDF_PATHS.includes(pdfPath)) {
    return disabledReliability(row.id, "unverified-pdf-path");
  }
  if (pdfPath !== "network-main-frame") {
    return disabledReliability(row.id, "uncontrolled-pdf-path");
  }
  if (row.family === "chromium") {
    return disabledReliability(row.id, "no-verified-blocking-native-hold");
  }
  if (row.family === "webkit") {
    return disabledReliability(row.id, "browser-interception-unverified");
  }
  return disabledReliability(row.id, "native-scan-interlock-unverified");
}

const UNKNOWN = Object.freeze({
  status: "unsupported-browser", browserId: null,
  automaticInterceptionDisabled: true,
  disabledReason: "unsupported-browser",
  observedDownloadEventsApi: false, observedDeclarativeRulesApi: false,
  observedWebRequestApi: false, observedFirefoxResponseFilterApi: false,
  automaticInterceptionEnabled: false, allPdfOpeningBlocked: false,
  permissionVerified: false, nativeScanInterlockVerified: false
});

function own(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  try {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    return descriptor && Object.hasOwn(descriptor, "value") ?
      descriptor.value : undefined;
  } catch {
    return undefined;
  }
}

function hasMethod(value, key) {
  return typeof own(value, key) === "function";
}

function hasEvent(value) {
  return hasMethod(value, "addListener") && hasMethod(value, "removeListener");
}

/**
 * Make a detached, read-only observation of an explicitly selected browser's
 * optional API shapes. No user-agent sniffing, permission requests, listeners,
 * network access or native scanner calls. API shape is NOT effective permission
 * or an assurance that the browser will intercept a PDF, particularly when
 * inline viewing, cache/blob/data/file, redirects and OS opens bypass events.
 *
 * Only a separately authenticated, explicitly opted-in browser integration
 * could ever enable interception after actual permission, version, response,
 * identity, native ClamAV and scan-before-open validation. This module cannot.
 */
export function assessAutomaticPdfInterception(browserId, api = {}) {
  if (typeof browserId !== "string") return UNKNOWN;
  const row = AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX.find(
    item => item.id === browserId
  );
  if (!row) return UNKNOWN;

  const dnr = own(api, "declarativeNetRequest");
  const webRequest = own(api, "webRequest");
  const flags = getBrowserCapabilityFlags(api);
  return Object.freeze({
    status: "inactive",
    browserId: row.id,
    automaticInterceptionDisabled: true,
    disabledReason: assessAutomaticInterceptionReliability(row.id).reason,
    observedDownloadEventsApi: flags.downloadEventsApi,
    observedDeclarativeRulesApi: hasMethod(dnr, "updateDynamicRules") &&
      hasMethod(dnr, "getDynamicRules"),
    observedWebRequestApi: hasEvent(own(webRequest, "onBeforeRequest")),
    observedFirefoxResponseFilterApi: row.id === "firefox" &&
      hasMethod(webRequest, "filterResponseData"),
    automaticInterceptionEnabled: false,
    allPdfOpeningBlocked: false,
    permissionVerified: false,
    nativeScanInterlockVerified: false
  });
}
