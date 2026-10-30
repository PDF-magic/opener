import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { classifyPdfDocumentResource as classify } from "../src/pdf-resource-scope.js";

const none = {
  isPdfCandidate: false, evidence: "none",
  authorizesScan: false, authorizesOpen: false
};
const yes = (evidence) => ({
  isPdfCandidate: true, evidence, authorizesScan: false, authorizesOpen: false
});
const event = (url = "https://example.test/report.pdf", extra = {}) => ({
  type: "main_frame", tabId: 12, frameId: 0, url, ...extra
});
const header = (value) => [{ name: "Content-Type", value }];

test("recognizes main-frame PDF document URL and validated response MIME", () => {
  for (const url of [
    "https://example.test/report.pdf",
    "https://example.test/a/%72eport%2EPDF?download=1",
    "file:///Users/example/Downloads/report.pdf"
  ]) assert.deepEqual(classify(event(url)), yes("document-url"));
  assert.deepEqual(classify(event("https://example.test/view?id=1", {
    responseHeaders: header("application/pdf")
  })), yes("document-response-mime"));
  assert.deepEqual(classify(event("https://example.test/download", {
    mimeType: "application/x-pdf; charset=UTF-8"
  })), yes("document-response-mime"));
});

test("ignores unrelated page subresources even with PDF filenames and MIME", () => {
  for (const type of [
    "script", "stylesheet", "image", "imageset", "font", "media",
    "xmlhttprequest", "fetch", "websocket", "ping", "csp_report",
    "object", "other", "web_manifest", "speculative"
  ]) {
    assert.deepEqual(classify(event("https://example.test/asset.pdf", { type })), none);
    assert.deepEqual(classify(event("https://example.test/asset.pdf", {
      type, frameId: 3, mimeType: "application/pdf",
      responseHeaders: header("application/pdf")
    })), none);
  }
});

test("handles a document subframe without admitting arbitrary page assets", () => {
  assert.deepEqual(classify(event("https://example.test/frame.pdf", {
    type: "sub_frame", frameId: 3
  })), yes("embedded-document-url"));
  assert.deepEqual(classify(event("https://example.test/frame.html", {
    type: "sub_frame", frameId: 3
  })), none);
  for (const extra of [
    { type: "sub_frame", frameId: 0 },
    { type: "sub_frame", frameId: 3, mimeType: "application/pdf" },
    { type: "sub_frame", frameId: 3, responseHeaders: header("application/pdf") },
    { type: "main_frame", frameId: 3 }
  ]) assert.deepEqual(classify(event("https://example.test/frame.pdf", extra)), none);
});

test("contradictory, missing and malformed declared MIME overrides .pdf hints", () => {
  for (const extra of [
    { mimeType: "text/html" }, { mimeType: "application/octet-stream" },
    { mimeType: "application/pdf; broken" }, { mimeType: null },
    { responseHeaders: header("image/png") }, { responseHeaders: [] },
    { responseHeaders: null },
    { responseHeaders: [...header("application/pdf"), ...header("application/pdf")] },
    { mimeType: "application/pdf", responseHeaders: header("text/html") }
  ]) assert.deepEqual(classify(event("https://example.test/file.pdf", extra)), none);
});

test("rejects unsupported URL schemes even if the browser claims PDF MIME", () => {
  for (const url of [
    "blob:https://example.test/file.pdf", "data:application/pdf,bytes",
    "javascript:alert(1)", "ftp://example.test/report.pdf",
    "chrome-extension://abc/file.pdf",
    "https://user:password@example.test/report.pdf",
    "https://example.test/file\n.pdf",
    "https://example.test/" + "a".repeat(8200) + ".pdf"
  ]) {
    assert.deepEqual(classify(event(url)), none, url);
    assert.deepEqual(classify(event(url, { mimeType: "application/pdf" })), none, url);
  }
  for (const url of [
    "https://example.test/file.pdf.js",
    "https://example.test/view?file=report.pdf",
    "https://example.test/a%2F.pdf",
    "https://example.test/a%00.pdf", "https://example.test/a%ZZ.pdf"
  ]) assert.deepEqual(classify(event(url)), none, url);
});

test("invalid frame context and hostile metadata fail closed", () => {
  for (const extra of [
    { type: "other" }, { type: undefined }, { tabId: -1 },
    { tabId: 1.5 }, { tabId: "12" }, { frameId: -1 },
    { frameId: 2 }, { frameId: "0" }, { frameId: undefined }
  ]) assert.deepEqual(classify(event(undefined, extra)), none);
  for (const bad of [null, undefined, 1, "", [], new URL("https://example.test/x.pdf")])
    assert.deepEqual(classify(bad), none);
  let reads = 0;
  const getter = event();
  Object.defineProperty(getter, "url", { get() {
    reads += 1;
    return "https://example.test/report.pdf";
  } });
  const inherited = Object.create(event());
  const hostile = new Proxy(event(), {
    getPrototypeOf() { throw Error("secret"); }
  });
  for (const record of [getter, inherited, hostile])
    assert.deepEqual(classify(record), none);
  assert.equal(reads, 0);
});

test("results are immutable, path-free and never authorize scan or open", () => {
  for (const record of [
    event("https://example.test/private.pdf?secret=value"),
    event("https://example.test/private.pdf?secret=value", {
      mimeType: "application/pdf"
    }),
    event("https://example.test/private.pdf?secret=value", { type: "image" })
  ]) {
    const result = classify(record);
    assert.equal(Object.isFrozen(result), true);
    assert.equal(result.authorizesScan, false);
    assert.equal(result.authorizesOpen, false);
    assert.deepEqual(Object.keys(result).sort(),
      ["authorizesOpen", "authorizesScan", "evidence", "isPdfCandidate"]);
    assert.equal(JSON.stringify(result).includes("private"), false);
    assert.equal(JSON.stringify(result).includes("secret"), false);
  }
});

test("does not add browser interception, permissions or scanner transport", async () => {
  const load = (path) => readFile(new URL(path, import.meta.url), "utf8");
  const [source, background, manifestSource, pkg] = await Promise.all([
    load("../src/pdf-resource-scope.js"), load("../src/background.js"),
    load("../manifest.json"), load("../package.json")
  ]);
  const manifest = JSON.parse(manifestSource);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.equal(JSON.parse(pkg).scripts.test.includes("tests/*.test.mjs"), true);
  for (const token of [
    "addListener(", "fetch(", "XMLHttpRequest", "WebSocket",
    "connectNative(", "sendNativeMessage(", "downloads.open(",
    "window.open(", "scan-and-open", "clamscan(", "node:fs",
    "querySelector(", "getElementsByTagName(", "console."
  ]) assert.equal(source.includes(token), false, token);
});
