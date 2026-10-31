import {
  AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX
} from "./automatic-interception-capability-matrix.js";

/**
 * Whether each supported browser exposes a *candidate* point for blocking
 * matching network requests before a PDF is rendered (opener-0781).
 *
 * This is a static, conservative assessment based on the existing researched
 * capability matrix. Vendor API availability is not effective permission,
 * an installed or tested feature, complete PDF identification, or an
 * extension/OS-wide pre-open interlock.
 */
export const PDF_INTERCEPTION_POINT_ASSESSMENT_VERSION = 1;

const UNCONTROLLED_PATHS = Object.freeze([
  "unmatched-or-redirected-network-requests",
  "inline-or-cached-pdf-rendering",
  "blob-data-and-file-urls",
  "browser-auto-open-and-other-extensions",
  "finder-and-other-operating-system-apps"
]);

function rulePoint(status) {
  if (status === "documented") return "documented-with-site-and-rule-grants";
  if (status === "safari-specific") {
    return "documented-safari-version-and-site-grants";
  }
  return "conditional-browser-version-and-site-grants";
}

function blockingPoint(status) {
  if (status === "documented-with-grants") {
    return "firefox-blocking-request-with-host-and-api-grants";
  }
  if (status === "policy-installed-only") {
    return "enterprise-policy-installed-only";
  }
  if (status === "conditional-policy") {
    return "conditional-enterprise-policy-installed-only";
  }
  return "not-established";
}

function streamPoint(status) {
  return status === "firefox-only-with-grants" ?
    "firefox-response-filter-with-additional-grants" : "not-established";
}

export const PDF_INTERCEPTION_POINT_ASSESSMENTS = Object.freeze(
  AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX.map(browser => Object.freeze({
    browserId: browser.id,
    family: browser.family,
    // Declarative rules can block matching NETWORK requests at rule evaluation
    // time. They cannot await a full ClamAV verdict on arbitrary PDF bytes.
    networkRequestRulePoint: rulePoint(browser.declarativeRules),
    requestBlockingListenerPoint: blockingPoint(browser.blockingWebRequest),
    responseBodyStreamPoint: streamPoint(browser.responseFilter),
    downloadEventPoint: browser.downloadEvents === "unverified" ?
      "not-established" : "observation-after-download-start-only",
    candidateScope: "matching-network-requests-only",
    // No installed/browser-version evidence or permission-granted route is
    // supplied by the research; this extension's background is inert.
    enforceableInCurrentExtension: false,
    verifiedInInstalledBrowser: false,
    effectiveSiteOrApiGrantsVerified: false,
    pdfIdentifiedBeforeRendering: false,
    fullResponseHeldForTrustedNativeScan: false,
    allPdfOpeningPathsBlocked: false,
    automaticInterceptionEnabled: false,
    bypassPaths: UNCONTROLLED_PATHS
  }))
);

const UNKNOWN = Object.freeze({
  status: "unsupported-browser",
  browserId: null,
  networkRequestRulePoint: "not-established",
  requestBlockingListenerPoint: "not-established",
  responseBodyStreamPoint: "not-established",
  downloadEventPoint: "not-established",
  candidateScope: "none",
  enforceableInCurrentExtension: false,
  verifiedInInstalledBrowser: false,
  effectiveSiteOrApiGrantsVerified: false,
  pdfIdentifiedBeforeRendering: false,
  fullResponseHeldForTrustedNativeScan: false,
  allPdfOpeningPathsBlocked: false,
  automaticInterceptionEnabled: false,
  bypassPaths: UNCONTROLLED_PATHS
});

/**
 * Read-only answer for one explicitly identified registered browser.
 * No user-agent probing, browser API invocation, privilege requests, network
 * interception, scan commands, file access, or side effects.
 */
export function getPdfInterceptionPointAssessment(browserId) {
  if (typeof browserId !== "string") return UNKNOWN;
  return PDF_INTERCEPTION_POINT_ASSESSMENTS.find(
    row => row.browserId === browserId
  ) ?? UNKNOWN;
}
