import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { detectPrivilegedPdfViewer } from "../src/pdf-privileged-viewer.js";

const none = {
  isPrivilegedPdfViewer: false, isPdfCandidate: false,
  evidence: "none", authorizesOpen: false
};
const viewer = {
  isPrivilegedPdfViewer: true, isPdfCandidate: false,
  evidence: "privileged-viewer-page", authorizesOpen: false
};
const detect = (url, options = {}) =>
  detectPrivilegedPdfViewer({ tabId: 3, frameId: 0, url, ...options });

test("recognizes exact browser-owned Chromium and Firefox PDF viewer shells", () => {
  for (const url of [
    "chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/index.html",
    "chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/index.html?src=private.pdf#toolbar=0",
    "resource://pdf.js/web/viewer.html",
    "resource://pdf.js/web/viewer.html?file=https%3A%2F%2Fexample.test%2Fprivate.pdf"
  ]) {
    assert.deepEqual(detect(url), viewer, url);
    assert.deepEqual(detect(url, { frameId: 4 }), viewer, url + " embedded");
  }
});

test("does not confuse arbitrary privileged pages, spoofed origins or lookalike paths with the viewer", () => {
  for (const url of [
    "chrome://settings/content/report.pdf",
    "chrome://pdf-viewer/index.html",
    "edge://pdf-viewer/index.html",
    "about:blank", "about:reader?url=https://example.test/a.pdf",
    "moz-extension://aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/web/viewer.html",
    "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/index.html",
    "chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/options.html",
    "chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/index.html/other",
    "chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/index.html%2Fother",
    "resource://other/web/viewer.html",
    "resource://pdf.js/web/viewer.html/other",
    "resource://pdf.js/web/viewer.html%2Fother",
    "https://example.test/chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/index.html",
    "https://mhjfbmdgcfjbbpaeojofohoefgiehjai/index.html",
    "blob:chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/index.html",
    "javascript:alert('resource://pdf.js/web/viewer.html')",
    "file:///web/viewer.html",
    "data:text/html,resource://pdf.js/web/viewer.html",
    "https://example.test/report.pdf",
    "chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/index.html".repeat(8193),
    "chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/index%ZZ.html"
  ]) assert.deepEqual(detect(url), none, url.slice(0, 120));
});

test("requires trusted navigation shape and rejects getters, proxies and malformed frames", () => {
  for (const options of [
    { tabId: -1 }, { tabId: undefined }, { tabId: "3" },
    { tabId: 1.5 }, { tabId: Number.MAX_SAFE_INTEGER + 1 },
    { frameId: -1 }, { frameId: undefined }, { frameId: "0" },
    { frameId: 1.5 }, { frameId: Number.MAX_SAFE_INTEGER + 1 }
  ]) assert.deepEqual(detect("resource://pdf.js/web/viewer.html", options), none);
  const getter = { tabId: 1, frameId: 0 };
  Object.defineProperty(getter, "url", { get() { throw Error("getter executed"); } });
  const inherited = Object.create({ url: "resource://pdf.js/web/viewer.html" });
  inherited.tabId = 1;
  inherited.frameId = 0;
  for (const value of [
    null, undefined, [], 3, "resource://pdf.js/web/viewer.html", getter, inherited,
    new URL("resource://pdf.js/web/viewer.html"),
    new Proxy({}, { getPrototypeOf() { throw Error("proxy invoked"); } }),
    { tabId: 1, frameId: 0, url: { toString() { throw Error("coercion"); } } }
  ]) assert.deepEqual(detectPrivilegedPdfViewer(value), none);
});

test("recognition never asserts PDF evidence, allows opening or exposes private URLs", () => {
  for (const result of [
    detect("chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/index.html?file=secret.pdf"),
    detect("resource://pdf.js/web/viewer.html#secret"),
    detect("https://example.test/private.pdf")
  ]) {
    assert.equal(Object.isFrozen(result), true);
    assert.deepEqual(Object.keys(result).sort(),
      ["authorizesOpen", "evidence", "isPdfCandidate", "isPrivilegedPdfViewer"]);
    assert.equal(result.isPdfCandidate, false);
    assert.equal(result.authorizesOpen, false);
    assert.doesNotMatch(JSON.stringify(result), /secret|private|example\.test/);
  }
});

test("passive detector leaves browser permissions and scanner inactive; required CI runs it", async () => {
  const load = (path) => readFile(new URL(path, import.meta.url), "utf8");
  const [source, background, manifestSource, safariSource, ci] = await Promise.all([
    load("../src/pdf-privileged-viewer.js"), load("../src/background.js"),
    load("../manifest.json"), load("../../safari/manifest.json"),
    load("../../../.github/workflows/ci.yml")
  ]);
  for (const forbidden of [
    "addListener(", "permissions.request", "connectNative", "sendNativeMessage",
    "window.open", "downloads.open", "fetch(", "XMLHttpRequest", "WebSocket",
    "node:fs", "scan-and-open", "ClamAV", "console."
  ]) assert.equal(source.includes(forbidden), false, forbidden);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  const manifest = JSON.parse(manifestSource);
  const safari = JSON.parse(safariSource);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.deepEqual(safari.host_permissions, []);
  assert.match(ci, /node --test tests\/pdf-privileged-viewer\.test\.mjs/);
});
