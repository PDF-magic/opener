import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  NON_BLOCKING_PDF_LIFECYCLE_EVENTS,
  assessPdfPreLoadInterceptionTrigger
} from "../src/pdf-preload-interception-trigger.js";
import {
  PDF_NAVIGATION_EVENT_PHASES
} from "../src/pdf-pre-render-navigation-events.js";
import {
  PDF_INTERCEPTION_POINT_ASSESSMENTS
} from "../src/pdf-interception-point-assessment.js";

const IDS = PDF_INTERCEPTION_POINT_ASSESSMENTS.map(item => item.browserId);
const nav = (url = "https://example.test/contract.pdf", patch = {}) =>
  ({ tabId: 19, frameId: 0, url, ...patch });
const request = (url = "https://example.test/contract.pdf", patch = {}) =>
  ({ ...nav(url), type: "main_frame", ...patch });
const assess = (browser, event, details) =>
  assessPdfPreLoadInterceptionTrigger(browser, event, details);
const read = path => readFile(new URL(path, import.meta.url), "utf8");

function assertNeverAuthorized(result) {
  assert.ok(Object.isFrozen(result));
  assert.equal(result.effectiveBlockingPointVerified, false);
  assert.equal(result.permissionVerified, false);
  assert.equal(result.pdfBytesVerified, false);
  assert.equal(result.nativeScanVerified, false);
  assert.equal(result.mayInitiateAutomaticInterception, false);
  assert.equal(result.allPdfOpeningPathsBlocked, false);
  assert.equal(result.authorizesScan, false);
  assert.equal(result.authorizesOpen, false);
  assert.doesNotMatch(JSON.stringify(result), /example\.test|contract\.pdf|token|secret/);
}

test("enumerates nonblocking or post-load lifecycle notifications without duplicates", () => {
  const expected = [
    "webNavigation.onCommitted", "webNavigation.onDOMContentLoaded",
    "webNavigation.onCompleted", "webNavigation.onErrorOccurred",
    "webNavigation.onHistoryStateUpdated",
    "webNavigation.onReferenceFragmentUpdated",
    "webRequest.onCompleted", "downloads.onCreated",
    "downloads.onChanged", "downloads.onErased", "tabs.onUpdated"
  ];
  assert.deepEqual(NON_BLOCKING_PDF_LIFECYCLE_EVENTS, expected);
  assert.ok(Object.isFrozen(NON_BLOCKING_PDF_LIFECYCLE_EVENTS));
  assert.equal(new Set(NON_BLOCKING_PDF_LIFECYCLE_EVENTS).size, expected.length);
});

test("all lifecycle notifications are rejected as interception triggers on every browser", () => {
  for (const browserId of IDS) {
    for (const event of NON_BLOCKING_PDF_LIFECYCLE_EVENTS) {
      const result = assess(browserId, event, nav(
        "https://example.test/contract.pdf?token=secret"
      ));
      assert.equal(result.status, "nonblocking-lifecycle-observation", event);
      assert.equal(result.phase, "not-a-veto");
      assert.equal(result.conditionalPreRequestBlockingCandidate, false);
      assert.equal(result.pdfEvidence, "none");
      assertNeverAuthorized(result);
    }
  }
});

test("the timeline's non-pre-render stages are always nonblocking", () => {
  for (const stage of PDF_NAVIGATION_EVENT_PHASES) {
    if (stage.potentiallyBeforeRender) continue;
    const details = stage.event.startsWith("webRequest.") ? request() : nav();
    const result = assess("firefox", stage.event, details);
    assert.equal(result.status, "nonblocking-lifecycle-observation", stage.event);
    assert.equal(result.conditionalPreRequestBlockingCandidate, false);
    assertNeverAuthorized(result);
  }
});

test("an early webNavigation event cannot synchronously cancel or hold a PDF", () => {
  for (const browserId of IDS) {
    const result = assess(browserId, "webNavigation.onBeforeNavigate", nav());
    assert.equal(result.status, "early-observation-only");
    assert.equal(result.phase, "before-navigation");
    assert.equal(result.pdfEvidence, "url-path-hint");
    assert.equal(result.conditionalPreRequestBlockingCandidate, false);
    assertNeverAuthorized(result);
  }
});

test("a before-request event is only a conditional Firefox blocking candidate", () => {
  const result = assess("firefox", "webRequest.onBeforeRequest", request());
  assert.equal(result.status, "conditional-firefox-request-block");
  assert.equal(result.phase, "before-network-request");
  assert.equal(result.conditionalPreRequestBlockingCandidate, true);
  assert.equal(result.pdfEvidence, "url-path-hint");
  assertNeverAuthorized(result);
});

test("ordinary Chromium MV3 cannot treat webRequest observation as an authorized veto", () => {
  for (const browserId of [
    "brave", "chrome", "chromium", "edge", "vivaldi", "opera", "arc"
  ]) {
    const result = assess(browserId, "webRequest.onBeforeRequest", request());
    assert.equal(result.status, "conditional-enterprise-request-block");
    assert.equal(result.conditionalPreRequestBlockingCandidate, true);
    assertNeverAuthorized(result);
  }
});

test("Safari has no established blocking webRequest listener point", () => {
  const result = assess("safari", "webRequest.onBeforeRequest", request());
  assert.equal(result.status, "no-blocking-listener-established");
  assert.equal(result.conditionalPreRequestBlockingCandidate, false);
  assertNeverAuthorized(result);
});

test("headers before body do not imply a cancellable native-scanner hold", () => {
  for (const browserId of IDS) {
    const result = assess(browserId, "webRequest.onHeadersReceived",
      request("https://example.test/download/52?token=private", {
        responseHeaders: [{ name: "Content-Type", value: "application/pdf" }]
      }));
    assert.equal(result.phase, "response-headers");
    assert.equal(result.status, "early-observation-only");
    assert.equal(result.pdfEvidence, "response-mime-hint");
    assert.equal(result.conditionalPreRequestBlockingCandidate, false);
    assertNeverAuthorized(result);
  }
});

test("a redirect notice cannot identify or veto the final PDF response", () => {
  const result = assess("firefox", "webRequest.onBeforeRedirect",
    request("https://example.test/contract.pdf", {
      redirectUrl: "https://other.test/landing.html", statusCode: 302
    }));
  assert.equal(result.status, "early-observation-only");
  assert.equal(result.phase, "before-redirect");
  assert.equal(result.pdfEvidence, "none");
  assert.equal(result.conditionalPreRequestBlockingCandidate, false);
  assertNeverAuthorized(result);
});

test("ambiguous resource types and subframes never become blocking candidates", () => {
  for (const details of [
    request(undefined, { type: "image" }),
    request(undefined, { type: "sub_frame" }),
    request(undefined, { frameId: 3 }),
    request(undefined, { tabId: -1 }),
    nav(), null, {}, [], request(undefined, { tabId: 1.25 })
  ]) {
    const result = assess("firefox", "webRequest.onBeforeRequest", details);
    assert.equal(result.status, "invalid-or-unavailable-event");
    assert.equal(result.conditionalPreRequestBlockingCandidate, false);
    assertNeverAuthorized(result);
  }
});

test("HTML or extensionless URLs do not produce verified PDF evidence", () => {
  for (const url of [
    "https://example.test/report.html",
    "https://example.test/download",
    "https://example.test/report.pdf?source=html",
    "data:application/pdf;base64,JVBERi0x",
    "blob:https://example.test/001"
  ]) {
    const result = assess("firefox", "webRequest.onBeforeRequest",
      request(url));
    // Suffix is a hint only, including a potentially deceptive .pdf URL.
    assert.equal(result.pdfBytesVerified, false);
    assert.equal(result.nativeScanVerified, false);
    assertNeverAuthorized(result);
  }
});

test("unsupported browser and unknown event fail closed", () => {
  for (const browserId of [undefined, "", "Chrome", "opera-gx", null, {}, []]) {
    const result = assess(browserId, "webRequest.onBeforeRequest", request());
    assert.equal(result.status, "unsupported-browser");
    assert.equal(result.browserId, null);
    assert.equal(result.conditionalPreRequestBlockingCandidate, false);
    assertNeverAuthorized(result);
  }
  for (const event of [undefined, null, "webRequest.onBeforeHeaders", "onCompleted",
    "declarativeNetRequest.onRuleMatchedDebug", {}, [], "webNavigation.onTabReplaced"]) {
    const result = assess("chrome", event, request());
    assert.ok(["unknown-event", "invalid-or-unavailable-event"].includes(result.status));
    assert.equal(result.conditionalPreRequestBlockingCandidate, false);
    assertNeverAuthorized(result);
  }
});

test("hostile metadata cannot leak private URL data or establish a candidate", () => {
  const getter = request();
  Object.defineProperty(getter, "tabId", { get() {
    throw Error("https://example.test/?token=private");
  } });
  const proxy = new Proxy(request(), {
    getPrototypeOf() { throw Error("private download"); }
  });
  for (const details of [getter, proxy, Object.create(request())]) {
    const result = assess("firefox", "webRequest.onBeforeRequest", details);
    assert.equal(result.status, "invalid-or-unavailable-event");
    assert.equal(result.conditionalPreRequestBlockingCandidate, false);
    assertNeverAuthorized(result);
  }
});

test("documentation explains why post-load observations cannot gate native scanning", async () => {
  const doc = await read("../src/pdf-preload-interception-trigger.md");
  for (const phrase of [
    "opener-0782", "after content has loaded", "onDOMContentLoaded",
    "onCompleted", "onCommitted", "onBeforeNavigate",
    "onHeadersReceived", "webRequest.onBeforeRequest",
    "enterprise", "Firefox", "Safari", "ClamAV",
    "scanner", "user preferences", "service worker"
  ]) assert.ok(doc.toLowerCase().includes(phrase.toLowerCase()), phrase);
  assert.match(doc, /pdf-pre-render-navigation-events\.js/);
  assert.match(doc, /pdf-interception-point-assessment\.js/);
});

test("the module cannot register listeners, change permissions or open unscanned files", async () => {
  const [source, manifest, safari, background, pkg, ci] = await Promise.all([
    read("../src/pdf-preload-interception-trigger.js"),
    read("../manifest.json").then(JSON.parse),
    read("../../safari/manifest.json").then(JSON.parse),
    read("../src/background.js"),
    read("../package.json").then(JSON.parse),
    read("../../../.github/workflows/ci.yml")
  ]);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.deepEqual(safari.permissions, ["nativeMessaging"]);
  assert.deepEqual(safari.host_permissions, []);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.match(pkg.scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(ci, /npm test/);
  for (const forbidden of [
    "globalThis.", "chrome.", "browser.", "navigator.userAgent",
    "addListener(", "permissions.request(", "fetch(", "XMLHttpRequest",
    "downloads.download(", "downloads.open(", "sendNativeMessage(",
    "connectNative(", "window.open(", "location.href", "localStorage",
    "sessionStorage", "node:fs", "scan-and-open"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
