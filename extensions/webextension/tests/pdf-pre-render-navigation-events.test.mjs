import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  identifyPdfPreRenderNavigationEvent as identify,
  PDF_NAVIGATION_EVENT_PHASES as phases
} from "../src/pdf-pre-render-navigation-events.js";

const nav = (url = "https://example.test/report.pdf", patch = {}) =>
  ({ tabId: 11, frameId: 0, url, ...patch });
const request = (url = "https://example.test/report.pdf", patch = {}) =>
  ({ ...nav(url), type: "main_frame", ...patch });
const classify = (name, details) => identify(name, details);

test("timeline enumerates the early navigation, request, redirect and header events", () => {
  assert.deepEqual(
    phases.filter(x => x.potentiallyBeforeRender).map(x => x.event),
    [
      "webNavigation.onBeforeNavigate", "webRequest.onBeforeRequest",
      "webRequest.onBeforeRedirect", "webRequest.onHeadersReceived"
    ]
  );
  assert.ok(Object.isFrozen(phases));
  for (const phase of phases) assert.equal(Object.isFrozen(phase), true);
  assert.equal(new Set(phases.map(x => x.event)).size, phases.length);
});

test("beforeNavigate can identify a PDF URL hint but not PDF content or rendering control", () => {
  const seen = classify("webNavigation.onBeforeNavigate",
    nav("https://example.test/download/Report%2Epdf?token=private"));
  assert.deepEqual(seen, {
    event: "webNavigation.onBeforeNavigate", stage: "before-navigation",
    potentiallyBeforeRender: true, pdfEvidence: "url-path-hint",
    verifiedPdf: false, interceptionEnabled: false,
    authorizesScan: false, authorizesOpen: false
  });
  assert.equal(Object.isFrozen(seen), true);
  assert.doesNotMatch(JSON.stringify(seen), /token|example\.test|Report/i);
});

test("beforeRequest exposes a preliminary network-stage URL hint only for main-frame requests", () => {
  const seen = classify("webRequest.onBeforeRequest", request());
  assert.equal(seen.stage, "before-network-request");
  assert.equal(seen.pdfEvidence, "url-path-hint");
  assert.equal(seen.potentiallyBeforeRender, true);
  for (const details of [
    request("https://example.test/report.pdf", { type: "image" }),
    request("https://example.test/report.pdf", { type: "sub_frame" }),
    request("https://example.test/report.pdf", { frameId: 5 }),
    request("https://example.test/report.pdf", { tabId: -1 })
  ]) assert.equal(classify("webRequest.onBeforeRequest", details).event, "unavailable");
});

test("redirect events cannot establish the final URL MIME or viewer behavior", () => {
  const response = classify("webRequest.onBeforeRedirect", request(
    "https://example.test/report.pdf",
    { redirectUrl: "https://another.test/landing.html", statusCode: 302 }
  ));
  assert.equal(response.stage, "before-redirect");
  assert.equal(response.potentiallyBeforeRender, true);
  assert.equal(response.pdfEvidence, "none");
  assert.equal(response.interceptionEnabled, false);
  assert.doesNotMatch(JSON.stringify(response), /landing|another|report/);
});

test("header-received events recognize extensionless PDF response hints, not verified bytes", () => {
  const value = classify("webRequest.onHeadersReceived",
    request("https://example.test/download/123", {
      responseHeaders: [{ name: "Content-Type", value: "application/pdf" }]
    }));
  assert.equal(value.stage, "response-headers");
  assert.equal(value.potentiallyBeforeRender, true);
  assert.equal(value.pdfEvidence, "response-mime-hint");
  assert.equal(value.verifiedPdf, false);
  assert.equal(value.authorizesScan, false);
});

test("HTML MIME at .pdf URLs, conflicting headers and absent response proof never claim a PDF", () => {
  for (const details of [
    request("https://example.test/report.pdf", {
      responseHeaders: [{ name: "Content-Type", value: "text/html" }]
    }),
    request("https://example.test/report.pdf", {
      responseHeaders: [{ name: "Content-Type", value: "text/html" },
        { name: "Content-Type", value: "application/pdf" }]
    }),
    request("https://example.test/report.pdf")
  ]) {
    const out = classify("webRequest.onHeadersReceived", details);
    assert.notEqual(out.pdfEvidence, "response-mime-hint");
  }
  assert.equal(classify("webRequest.onHeadersReceived",
    request("https://example.test/report.pdf", {
      responseHeaders: [{ name: "Content-Type", value: "text/html" }]
    })).pdfEvidence, "html-response");
});

test("commit, DOM ready and completion do not supply an assured pre-render hook", () => {
  for (const [event,stage] of [
    ["webNavigation.onCommitted","committed"],
    ["webNavigation.onDOMContentLoaded","dom-loaded"],
    ["webNavigation.onCompleted","navigation-completed"],
    ["webNavigation.onErrorOccurred","navigation-error"],
    ["webRequest.onCompleted","request-completed"]
  ]) {
    const details = event.startsWith("webNavigation.") ? nav() : request();
    const out = classify(event, details);
    assert.equal(out.stage, stage);
    assert.equal(out.potentiallyBeforeRender, false);
    assert.equal(out.pdfEvidence, "none");
    assert.equal(out.interceptionEnabled, false);
  }
  assert.equal(classify("downloads.onCreated", request()).event, "unavailable");
  assert.equal(classify("webNavigation.onHistoryStateUpdated", nav()).event, "unavailable");
});

test("simulated successful navigation order does not turn candidates into a blocking gate", () => {
  const events = [
    "webNavigation.onBeforeNavigate", "webNavigation.onCommitted",
    "webNavigation.onDOMContentLoaded", "webNavigation.onCompleted"
  ];
  const results = events.map(event => classify(event, nav()));
  assert.deepEqual(results.map(x => x.stage), [
    "before-navigation", "committed", "dom-loaded", "navigation-completed"
  ]);
  assert.deepEqual(results.map(x => x.potentiallyBeforeRender),
    [true, false, false, false]);
  assert.ok(results.every(x => !x.interceptionEnabled && !x.authorizesOpen));
});

test("unknown, malformed, non-document and hostile metadata fail closed without leaking URLs", () => {
  const getter = nav();
  Object.defineProperty(getter, "frameId", { get() { throw Error("/secret.pdf"); } });
  for (const value of [
    null, undefined, [], {}, { ...nav(), tabId: 1.5 },
    { ...nav(), frameId: 1 }, getter,
    new Proxy({}, { getPrototypeOf() { throw Error("secret"); } })
  ]) {
    const out = classify("webNavigation.onBeforeNavigate", value);
    assert.equal(out.event, "unavailable");
    assert.doesNotMatch(JSON.stringify(out), /secret|https|\.pdf/i);
  }
  assert.equal(classify("webRequest.onBeforeRequest", nav()).event, "unavailable");
  assert.equal(classify("webNavigation.onBeforeNavigate", nav("data:application/pdf,secret")).pdfEvidence,"none");
  assert.equal(classify("webNavigation.onBeforeNavigate", nav("blob:https://example.test/1")).pdfEvidence,"none");
});

test("docs explain pre-render limits, undefined cross-API ordering and missing browser proof", async () => {
  const docs = await readFile(new URL("../src/pdf-pre-render-navigation-events.md", import.meta.url),"utf8");
  for (const term of [
    "onBeforeNavigate", "onBeforeRequest", "onHeadersReceived",
    "onBeforeRedirect", "onCommitted", "onDOMContentLoaded", "onCompleted",
    "no guaranteed ordering", "not a synchronous veto", "cached",
    "blob:", "Safari", "Firefox", "redirect", "Content-Type",
    "browser-specific live experiments"
  ]) assert.ok(docs.includes(term), term);
  assert.match(docs, /developer\.chrome\.com\/docs\/extensions\/reference\/api\/webNavigation/);
  assert.match(docs, /developer\.mozilla\.org\/en-US\/docs\/Mozilla\/Add-ons\/WebExtensions\/API\/webRequest\/onHeadersReceived/);
});

test("classification remains passive without adding interception privileges or changing scanner settings", async () => {
  const read = path => readFile(new URL(path, import.meta.url), "utf8");
  const [source, manifestText, safariText, background, ci] = await Promise.all([
    read("../src/pdf-pre-render-navigation-events.js"),
    read("../manifest.json"), read("../../safari/manifest.json"),
    read("../src/background.js"), read("../../../.github/workflows/ci.yml")
  ]);
  const manifest=JSON.parse(manifestText),safari=JSON.parse(safariText);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.deepEqual(safari.host_permissions, []);
  assert.deepEqual(safari.permissions, ["nativeMessaging"]);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  assert.match(ci, /node --test tests\/pdf-pre-render-navigation-events\.test\.mjs/);
  for (const forbidden of [
    "addListener(", "webRequestBlocking", "permissions.request(",
    "sendNativeMessage(", "connectNative(", "downloads.open(",
    "fetch(", "XMLHttpRequest", "globalThis.", "chrome.", "browser."
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
