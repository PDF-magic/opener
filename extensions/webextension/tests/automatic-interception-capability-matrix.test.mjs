import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX,
  AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX_VERSION,
  assessAutomaticPdfInterception
} from "../src/automatic-interception-capability-matrix.js";

const IDS = [
  "brave", "chrome", "chromium", "edge", "vivaldi",
  "opera", "arc", "firefox", "safari"
];
const event = () => ({ addListener() {}, removeListener() {} });
function fullApi() {
  return {
    runtime: { getManifest() {}, getURL() {} },
    downloads: {
      onCreated: event(), onChanged: event(), onErased: event()
    },
    declarativeNetRequest: {
      updateDynamicRules() {}, getDynamicRules() {}
    },
    webRequest: {
      onBeforeRequest: event(), filterResponseData() {}
    }
  };
}
const load = path => readFile(new URL(path, import.meta.url), "utf8");

test("matrix covers every registered macOS browser exactly once", async () => {
  const registry = await load("../../../browser_registry.py");
  const rows = [...registry.matchAll(/^\s*"([a-z]+)": "([A-Za-z0-9.-]+)",?\s*$/gm)];
  assert.equal(AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX_VERSION, 1);
  assert.deepEqual(rows.map(row => row[1]), IDS);
  assert.deepEqual(AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX.map(row => row.id), IDS);
  assert.equal(new Set(IDS).size, IDS.length);
  assert.equal(AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX.length, 9);
});

test("all rows are immutable and report the shipped feature as inactive", () => {
  assert.ok(Object.isFrozen(AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX));
  for (const row of AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX) {
    assert.ok(Object.isFrozen(row));
    assert.equal(row.deployment, "inactive");
    assert.equal(row.permissionState, "not-verified");
    assert.equal(row.liveBrowserTested, false);
    assert.equal(row.allPdfOpeningBlocked, false);
    assert.equal(row.nativeScanInterlockVerified, false);
    assert.ok(["chromium", "gecko", "webkit"].includes(row.family));
    assert.ok(["documented", "conditional", "safari-specific"].includes(
      row.declarativeRules));
  }
  assert.throws(() => {
    AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX[0].deployment = "active";
  }, TypeError);
});

test("Chromium MV3 blocking requests are never promoted to normal-extension availability", () => {
  for (const row of AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX) {
    if (row.family !== "chromium") continue;
    assert.ok(["policy-installed-only", "conditional-policy"].includes(
      row.blockingWebRequest));
    assert.equal(row.responseFilter, "unverified");
  }
  assert.equal(AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX.find(
    row => row.id === "chrome").blockingWebRequest, "policy-installed-only");
  assert.equal(AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX.find(
    row => row.id === "edge").blockingWebRequest, "policy-installed-only");
});

test("Firefox-specific response filtering is not claimed for other browsers", () => {
  const fox = AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX.find(
    row => row.id === "firefox");
  assert.equal(fox.family, "gecko");
  assert.equal(fox.blockingWebRequest, "documented-with-grants");
  assert.equal(fox.responseFilter, "firefox-only-with-grants");
  for (const row of AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX) {
    if (row.id !== "firefox") assert.equal(row.responseFilter, "unverified");
  }
});

test("Safari remains version-and-permission-dependent and unverified for downloads", () => {
  const row = AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX.at(-1);
  assert.equal(row.id, "safari");
  assert.equal(row.family, "webkit");
  assert.equal(row.declarativeRules, "safari-specific");
  assert.equal(row.blockingWebRequest, "unverified");
  assert.equal(row.downloadEvents, "unverified");
  assert.equal(row.allPdfOpeningBlocked, false);
});

test("full API shapes are observations only, never native permission or interception", () => {
  for (const id of IDS) {
    const report = assessAutomaticPdfInterception(id, fullApi());
    assert.equal(report.status, "inactive");
    assert.equal(report.browserId, id);
    assert.equal(report.observedDownloadEventsApi, true);
    assert.equal(report.observedDeclarativeRulesApi, true);
    assert.equal(report.observedWebRequestApi, true);
    assert.equal(report.observedFirefoxResponseFilterApi, id === "firefox");
    assert.equal(report.automaticInterceptionEnabled, false);
    assert.equal(report.allPdfOpeningBlocked, false);
    assert.equal(report.permissionVerified, false);
    assert.equal(report.nativeScanInterlockVerified, false);
    assert.ok(Object.isFrozen(report));
    assert.equal("authorizesOpen" in report, false);
    assert.equal("scanVerified" in report, false);
  }
});

test("missing or partial API shapes do not imply actual support", () => {
  for (const id of IDS) {
    const report = assessAutomaticPdfInterception(id);
    assert.equal(report.observedDownloadEventsApi, false);
    assert.equal(report.observedDeclarativeRulesApi, false);
    assert.equal(report.observedWebRequestApi, false);
    assert.equal(report.observedFirefoxResponseFilterApi, false);
    assert.equal(report.automaticInterceptionEnabled, false);
  }
  const partial = fullApi();
  delete partial.downloads.onErased.removeListener;
  delete partial.declarativeNetRequest.getDynamicRules;
  delete partial.webRequest.onBeforeRequest.removeListener;
  assert.deepEqual({
    d: assessAutomaticPdfInterception("firefox", partial).observedDownloadEventsApi,
    n: assessAutomaticPdfInterception("firefox", partial).observedDeclarativeRulesApi,
    w: assessAutomaticPdfInterception("firefox", partial).observedWebRequestApi
  }, { d: false, n: false, w: false });
});

test("unknown browser IDs and unsupported inputs fail closed", () => {
  for (const id of [
    undefined, null, "", "Chrome", "opera-gx", "safari ", "unknown",
    42, {}, [], new String("chrome")
  ]) {
    const report = assessAutomaticPdfInterception(id, fullApi());
    assert.equal(report.status, "unsupported-browser");
    assert.equal(report.browserId, null);
    assert.equal(report.automaticInterceptionEnabled, false);
    assert.equal(report.permissionVerified, false);
    assert.ok(Object.isFrozen(report));
  }
});

test("accessor or hostile proxy APIs cannot be invoked or enable any feature", () => {
  let calls = 0;
  const apis = fullApi();
  for (const part of [apis.declarativeNetRequest, apis.webRequest]) {
    for (const key of Object.keys(part)) {
      if (typeof part[key] === "function") part[key] = () => {
        calls++; throw Error("must not call browser method");
      };
    }
  }
  const report = assessAutomaticPdfInterception("firefox", apis);
  assert.equal(report.observedDeclarativeRulesApi, true);
  assert.equal(report.observedWebRequestApi, true);
  assert.equal(calls, 0);
  const dangerous = Object.create(null);
  Object.defineProperty(dangerous, "webRequest", { get() {
    calls++; throw Error("private page URL");
  } });
  const hostile = new Proxy({}, {
    getOwnPropertyDescriptor() { throw Error("private PDF"); }
  });
  for (const api of [dangerous, hostile]) {
    const report = assessAutomaticPdfInterception("chrome", api);
    assert.equal(report.status, "inactive");
    assert.equal(report.observedWebRequestApi, false);
    assert.equal(report.automaticInterceptionEnabled, false);
  }
  assert.equal(calls, 0);
});

test("documentation distinguishes static vendor evidence from effective deployment", async () => {
  const doc = await load("../src/automatic-interception-capability-matrix.md");
  for (const row of AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX) {
    assert.ok(doc.includes(row.name), row.id);
  }
  for (const phrase of [
    "opener-0778", "inactive for all browsers", "API *shapes*",
    "No browser", "native ClamAV", "user's selected",
    "strict", "Finder", "explicitly", "opener-0777"
  ]) assert.ok(doc.toLowerCase().includes(phrase.toLowerCase()), phrase);
  assert.match(doc, /browser-interception-apis\.md/);
  assert.match(doc, /download-opening-browser-support\.md/);
});

test("existing manifests, background and CI stay safely disabled", async () => {
  const [shared, safari, background, source, packageJson, ci] = await Promise.all([
    load("../manifest.json").then(JSON.parse),
    load("../../safari/manifest.json").then(JSON.parse),
    load("../src/background.js"),
    load("../src/automatic-interception-capability-matrix.js"),
    load("../package.json").then(JSON.parse),
    load("../../../.github/workflows/ci.yml")
  ]);
  assert.deepEqual(shared.permissions, []);
  assert.deepEqual(shared.host_permissions, []);
  assert.deepEqual(shared.optional_permissions, ["downloads"]);
  assert.deepEqual(safari.permissions, ["nativeMessaging"]);
  assert.deepEqual(safari.host_permissions, []);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.match(packageJson.scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(ci, /npm test/);
  for (const forbidden of [
    "globalThis.", "chrome.", "browser.", "navigator.userAgent",
    "addListener(", "permissions.request(", "fetch(", "XMLHttpRequest",
    "downloads.download(", "downloads.open(", "sendNativeMessage(",
    "connectNative(", "window.open(", "location.href", "localStorage",
    "sessionStorage", "node:fs", "scan-and-open"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
