import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  PDF_INTERCEPTION_ASSURANCE_KINDS, describePdfInterceptionAssurance
} from "../src/pdf-interception-assurance.js";
import {
  PDF_INTERCEPTION_POINT_ASSESSMENTS
} from "../src/pdf-interception-point-assessment.js";

const browsers = PDF_INTERCEPTION_POINT_ASSESSMENTS.map(row => row.browserId);
const assess = describePdfInterceptionAssurance;
const read = path => readFile(new URL(path, import.meta.url), "utf8");

function neverEnforced(result) {
  assert.ok(Object.isFrozen(result));
  assert.equal(result.activeMonitoringVerified, false);
  assert.equal(result.effectiveRequestBlockingVerified, false);
  assert.equal(result.nativeScanBeforeRenderVerified, false);
  assert.equal(result.allPdfOpeningPathsBlocked, false);
  assert.equal(result.mayClaimEnforcedProtection, false);
  assert.equal(result.authorizesScan, false);
  assert.equal(result.authorizesOpen, false);
  assert.doesNotMatch(JSON.stringify(result), /example\.test|token=|private\/|pdfBytes/);
}

test("defines mutually exclusive inactive, observational, and conditional categories", () => {
  assert.deepEqual(PDF_INTERCEPTION_ASSURANCE_KINDS, [
    "inactive", "best-effort-monitoring", "unverified-request-blocking-candidate"
  ]);
  assert.ok(Object.isFrozen(PDF_INTERCEPTION_ASSURANCE_KINDS));
  assert.equal(new Set(PDF_INTERCEPTION_ASSURANCE_KINDS).size, 3);
});

test("every browser defaults to inactive, not silently to monitoring or enforcement", () => {
  assert.equal(browsers.length, 9);
  for (const browserId of browsers) {
    const item = assess(browserId);
    assert.equal(item.browserId, browserId);
    assert.equal(item.observation, null);
    assert.equal(item.status, "inactive");
    assert.equal(item.assuranceKind, "inactive");
    assert.equal(item.scope, "none");
    assert.match(item.displayLabel, /inactive/i);
    assert.equal(item.potentialBlockingPoint, false);
    neverEnforced(item);
  }
});

test("navigation and download lifecycle notifications remain best-effort observations", () => {
  const observations = [
    "webNavigation.onBeforeNavigate", "webNavigation.onCommitted",
    "webNavigation.onDOMContentLoaded", "webNavigation.onCompleted",
    "webNavigation.onErrorOccurred", "webNavigation.onHistoryStateUpdated",
    "webNavigation.onReferenceFragmentUpdated",
    "webRequest.onBeforeRedirect", "webRequest.onHeadersReceived",
    "webRequest.onCompleted", "declarativeNetRequest.onRuleMatchedDebug",
    "downloads.onCreated", "downloads.onChanged", "downloads.onErased",
    "tabs.onUpdated"
  ];
  for (const browserId of browsers) for (const event of observations) {
    const item = assess(browserId, event);
    assert.equal(item.status, "observation-only");
    assert.equal(item.assuranceKind, "best-effort-monitoring");
    assert.equal(item.scope, "browser-event-observation-only");
    assert.equal(item.potentialBlockingPoint, false);
    assert.match(item.displayLabel, /cannot|not blocked/i);
    neverEnforced(item);
  }
});

test("a DNR rule-matched event is not evidence the rule blocked or scanned a PDF", () => {
  for (const browserId of browsers) {
    const item = assess(browserId, "declarativeNetRequest.onRuleMatchedDebug");
    assert.equal(item.status, "observation-only");
    assert.equal(item.potentialBlockingPoint, false);
    neverEnforced(item);
  }
});

test("Firefox and policy-conditional Chromium request listeners are only candidates", () => {
  for (const browserId of [
    "firefox", "chrome", "edge", "brave", "chromium", "opera", "vivaldi", "arc"
  ]) {
    const item = assess(browserId, "webRequest.onBeforeRequest");
    assert.equal(item.status, "blocking-point-unverified");
    assert.equal(item.assuranceKind, "unverified-request-blocking-candidate");
    assert.equal(item.scope, "matching-network-requests-only");
    assert.equal(item.potentialBlockingPoint, true);
    assert.match(item.displayLabel, /not scan-before-open enforcement/i);
    neverEnforced(item);
  }
});

test("Safari request event cannot be promoted to an unsupported blocking point", () => {
  const item = assess("safari", "webRequest.onBeforeRequest");
  assert.equal(item.assuranceKind, "best-effort-monitoring");
  assert.equal(item.status, "observation-only");
  assert.equal(item.potentialBlockingPoint, false);
  neverEnforced(item);
});

test("unknown browsers and events fail closed without exposing caller data", () => {
  for (const bad of [undefined, null, "", "Chrome", "unknown", {}, [], 1]) {
    const item = assess(bad, "webRequest.onBeforeRequest");
    assert.equal(item.status, "unsupported-browser");
    assert.equal(item.browserId, null);
    assert.equal(item.assuranceKind, "inactive");
    neverEnforced(item);
  }
  for (const bad of [
    "", false, undefined, 1, {}, [], Symbol("private"),
    "native-clean-scan", "scan-complete", "enforced",
    "https://example.test/private.pdf?token=secret",
    "webRequest.onBeforeRequest?token=secret",
    "webRequest.onBeforeRequest."
  ]) {
    const item = assess("firefox", bad);
    assert.equal(item.status, "unknown-observation");
    assert.equal(item.observation, null);
    assert.equal(item.assuranceKind, "inactive");
    neverEnforced(item);
  }
});

test("metadata cannot pretend to confer enforcement or scanner authority", () => {
  const untrusted = {
    event: "webRequest.onBeforeRequest", effectiveBlocking: true,
    scanVerified: true, allPdfOpeningPathsBlocked: true,
    url: "https://example.test/private.pdf?token=secret"
  };
  const item = assess("firefox", untrusted);
  assert.equal(item.status, "unknown-observation");
  neverEnforced(item);
  assert.equal(JSON.stringify(item).includes("secret"), false);
  const candidate = assess("firefox", "webRequest.onBeforeRequest");
  assert.equal(Object.isFrozen(candidate), true);
  assert.throws(() => { candidate.authorizesOpen = true; }, TypeError);
  assert.equal(candidate.authorizesOpen, false);
});

test("documentation distinguishes observed coverage, candidate request blocks and actual native enforcement", async () => {
  const doc = await read("../src/pdf-interception-assurance.md");
  for (const phrase of [
    "opener-0798", "best-effort", "enforcement", "scan-before-render",
    "ClamAV", "permissions", "browser", "user preferences",
    "inactive", "download", "matching network requests"
  ]) assert.ok(doc.toLowerCase().replace(/\s+/g, " ").includes(phrase.toLowerCase()), phrase);
});

test("classifier does not activate interception or modify browser and scanner settings", async () => {
  const [code, background, manifest, safari, pkg, ci] = await Promise.all([
    read("../src/pdf-interception-assurance.js"),
    read("../src/background.js"),
    read("../manifest.json").then(JSON.parse),
    read("../../safari/manifest.json").then(JSON.parse),
    read("../package.json").then(JSON.parse),
    read("../../../.github/workflows/ci.yml")
  ]);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(safari.permissions, ["nativeMessaging"]);
  assert.deepEqual(safari.host_permissions, []);
  assert.match(pkg.scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(ci, /npm test/);
  for (const forbidden of [
    "globalThis.", "chrome.", "browser.", "addListener(", "sendNativeMessage(",
    "connectNative(", "fetch(", "downloads.open(", "permissions.request(",
    "storage.local", "node:fs", "clamscan(", "window.open("
  ]) assert.equal(code.includes(forbidden), false, forbidden);
});
