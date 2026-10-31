import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  PDF_INTERCEPTION_POINT_ASSESSMENT_VERSION,
  PDF_INTERCEPTION_POINT_ASSESSMENTS,
  getPdfInterceptionPointAssessment
} from "../src/pdf-interception-point-assessment.js";
import {
  AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX
} from "../src/automatic-interception-capability-matrix.js";

const IDS = [
  "brave", "chrome", "chromium", "edge", "vivaldi",
  "opera", "arc", "firefox", "safari"
];
const read = path => readFile(new URL(path, import.meta.url), "utf8");

test("each registered browser receives one distinct deterministic point assessment", async () => {
  const registry = await read("../../../browser_registry.py");
  const ids = [...registry.matchAll(/^\s*"([a-z]+)": "[A-Za-z0-9.-]+",?\s*$/gm)]
    .map(matches => matches[1]);
  assert.equal(PDF_INTERCEPTION_POINT_ASSESSMENT_VERSION, 1);
  assert.deepEqual(ids, IDS);
  assert.deepEqual(PDF_INTERCEPTION_POINT_ASSESSMENTS.map(row => row.browserId), IDS);
  assert.equal(new Set(PDF_INTERCEPTION_POINT_ASSESSMENTS.map(row => row.browserId)).size, 9);
  assert.deepEqual(PDF_INTERCEPTION_POINT_ASSESSMENTS.map(row => row.family),
    AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX.map(row => row.family));
});

test("known vendor API research and point assessments stay in sync without duplicated grants", async () => {
  const vendor = JSON.parse(
    await read("../../../docs/browser-automatic-interception-capabilities.json")
  );
  assert.deepEqual(vendor.browsers.map(row => row.id), IDS);
  for (const item of vendor.browsers) {
    const decision = getPdfInterceptionPointAssessment(item.id);
    const actualRule = item.declarativeRules === "documented" ?
      (item.id === "safari" ? "documented-safari-version-and-site-grants" :
        "documented-with-site-and-rule-grants") :
      "conditional-browser-version-and-site-grants";
    assert.equal(decision.networkRequestRulePoint, actualRule, item.id);
    const listener = item.blockingWebRequest === "documented" ?
      "firefox-blocking-request-with-host-and-api-grants" :
      item.blockingWebRequest === "policy-installed-only" ?
        "enterprise-policy-installed-only" :
        item.blockingWebRequest === "conditional-policy-installed-only" ?
          "conditional-enterprise-policy-installed-only" : "not-established";
    assert.equal(decision.requestBlockingListenerPoint, listener, item.id);
    assert.equal(decision.responseBodyStreamPoint,
      item.responseBodyFilter === "documented-firefox-only" ?
        "firefox-response-filter-with-additional-grants" : "not-established");
    assert.equal(decision.downloadEventPoint,
      item.downloadEvents === "not-established" ?
        "not-established" : "observation-after-download-start-only");
  }
});

test("documented declarative request blocks are conditional even on Chrome and Edge", () => {
  for (const id of ["chrome", "edge"]) {
    const row = getPdfInterceptionPointAssessment(id);
    assert.equal(row.networkRequestRulePoint, "documented-with-site-and-rule-grants");
    assert.equal(row.requestBlockingListenerPoint, "enterprise-policy-installed-only");
    assert.equal(row.candidateScope, "matching-network-requests-only");
    assert.equal(row.enforceableInCurrentExtension, false);
  }
});

test("Chromium forks do not inherit a verified installed interception point", () => {
  for (const id of ["brave", "chromium", "vivaldi", "opera", "arc"]) {
    const row = getPdfInterceptionPointAssessment(id);
    assert.equal(row.networkRequestRulePoint,
      "conditional-browser-version-and-site-grants");
    assert.equal(row.requestBlockingListenerPoint,
      "conditional-enterprise-policy-installed-only");
    assert.equal(row.verifiedInInstalledBrowser, false);
    assert.equal(row.effectiveSiteOrApiGrantsVerified, false);
  }
});

test("Firefox can conditionally block a request or filter its stream, not claim native scan coverage", () => {
  const row = getPdfInterceptionPointAssessment("firefox");
  assert.equal(row.networkRequestRulePoint, "documented-with-site-and-rule-grants");
  assert.equal(row.requestBlockingListenerPoint,
    "firefox-blocking-request-with-host-and-api-grants");
  assert.equal(row.responseBodyStreamPoint,
    "firefox-response-filter-with-additional-grants");
  assert.equal(row.fullResponseHeldForTrustedNativeScan, false);
  assert.equal(row.pdfIdentifiedBeforeRendering, false);
});

test("Safari has Safari-specific rule support and no assumed blocking listeners", () => {
  const row = getPdfInterceptionPointAssessment("safari");
  assert.equal(row.networkRequestRulePoint,
    "documented-safari-version-and-site-grants");
  assert.equal(row.requestBlockingListenerPoint, "not-established");
  assert.equal(row.responseBodyStreamPoint, "not-established");
  assert.equal(row.downloadEventPoint, "not-established");
  assert.equal(row.enforceableInCurrentExtension, false);
});

test("downloads observation is not a network decision or browser open veto", () => {
  for (const row of PDF_INTERCEPTION_POINT_ASSESSMENTS) {
    if (row.browserId !== "safari") {
      assert.equal(row.downloadEventPoint, "observation-after-download-start-only");
    }
    assert.notEqual(row.downloadEventPoint, row.networkRequestRulePoint);
    assert.equal(row.allPdfOpeningPathsBlocked, false);
  }
});

test("no browser exposes an enabled and verified native-scan-before-render gate", () => {
  for (const row of PDF_INTERCEPTION_POINT_ASSESSMENTS) {
    assert.equal(row.enforceableInCurrentExtension, false, row.browserId);
    assert.equal(row.verifiedInInstalledBrowser, false, row.browserId);
    assert.equal(row.effectiveSiteOrApiGrantsVerified, false, row.browserId);
    assert.equal(row.pdfIdentifiedBeforeRendering, false, row.browserId);
    assert.equal(row.fullResponseHeldForTrustedNativeScan, false, row.browserId);
    assert.equal(row.allPdfOpeningPathsBlocked, false, row.browserId);
    assert.equal(row.automaticInterceptionEnabled, false, row.browserId);
    assert.ok(Object.isFrozen(row));
  }
});

test("uncontrolled opening paths are immutable and never represented as intercepted", () => {
  const expected = [
    "unmatched-or-redirected-network-requests",
    "inline-or-cached-pdf-rendering",
    "blob-data-and-file-urls",
    "browser-auto-open-and-other-extensions",
    "finder-and-other-operating-system-apps"
  ];
  for (const row of PDF_INTERCEPTION_POINT_ASSESSMENTS) {
    assert.deepEqual(row.bypassPaths, expected);
    assert.ok(Object.isFrozen(row.bypassPaths));
    assert.equal(row.allPdfOpeningPathsBlocked, false);
  }
});

test("unknown browsers and malformed inputs fail closed", () => {
  for (const unknown of [
    undefined, null, "", "Chrome", "firefox ", "safari-web", {},
    [], 10, new String("chrome")
  ]) {
    const row = getPdfInterceptionPointAssessment(unknown);
    assert.equal(row.status, "unsupported-browser");
    assert.equal(row.browserId, null);
    assert.equal(row.candidateScope, "none");
    assert.equal(row.enforceableInCurrentExtension, false);
    assert.equal(row.automaticInterceptionEnabled, false);
    assert.ok(Object.isFrozen(row));
  }
});

test("read-only assessment does not invoke browser APIs or access outside data", () => {
  const api = new Proxy({}, {
    get() { throw new Error("must not read browser state"); }
  });
  assert.strictEqual(getPdfInterceptionPointAssessment("firefox", api),
    getPdfInterceptionPointAssessment("firefox"));
  assert.ok(Object.isFrozen(PDF_INTERCEPTION_POINT_ASSESSMENTS));
  assert.throws(() => {
    PDF_INTERCEPTION_POINT_ASSESSMENTS[0].automaticInterceptionEnabled = true;
  }, TypeError);
  assert.throws(() => {
    PDF_INTERCEPTION_POINT_ASSESSMENTS[0].bypassPaths.push("unsafe");
  }, TypeError);
});

test("documentation records a per-browser enforceability verdict and distinct scopes", async () => {
  const doc = await read("../src/pdf-interception-point-assessment.md");
  for (const name of [
    "Brave", "Google Chrome", "Chromium", "Microsoft Edge", "Vivaldi",
    "Opera", "Arc", "Mozilla Firefox", "Apple Safari"
  ]) assert.ok(doc.includes(name), name);
  for (const term of [
    "opener-0781", "before", "matching network", "Firefox",
    "Safari", "enterprise", "site permission", "ClamAV", "Finder",
    "worker", "inline", "not implemented", "user preferences"
  ]) assert.ok(doc.toLowerCase().includes(term.toLowerCase()), term);
  assert.match(doc, /browser-automatic-interception-capabilities\.json/);
  assert.match(doc, /automatic-interception-capability-matrix\.js/);
});

test("CI discovers regression tests without changing browser permissions or scanner behavior", async () => {
  const [shared, safari, background, source, packageJson, workflow] =
    await Promise.all([
      read("../manifest.json").then(JSON.parse),
      read("../../safari/manifest.json").then(JSON.parse),
      read("../src/background.js"),
      read("../src/pdf-interception-point-assessment.js"),
      read("../package.json").then(JSON.parse),
      read("../../../.github/workflows/ci.yml")
    ]);
  assert.deepEqual(shared.permissions, []);
  assert.deepEqual(shared.host_permissions, []);
  assert.deepEqual(shared.optional_permissions, ["downloads"]);
  assert.deepEqual(safari.permissions, ["nativeMessaging"]);
  assert.deepEqual(safari.host_permissions, []);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.match(packageJson.scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(workflow, /npm test/);
  for (const forbidden of [
    "globalThis.", "navigator.userAgent", "addListener(", "permissions.request(",
    "fetch(", "XMLHttpRequest", "downloads.download(", "downloads.open(",
    "sendNativeMessage(", "connectNative(", "window.open(", "location.href",
    "localStorage", "sessionStorage", "node:fs", "scan-and-open"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
