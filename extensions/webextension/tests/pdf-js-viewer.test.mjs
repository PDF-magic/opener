import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { detectJavascriptPdfViewer } from "../src/pdf-js-viewer.js";

const NONE = { isPdfCandidate: false, evidence: "none", authorizesOpen: false };
const PDF = { isPdfCandidate: true, evidence: "javascript-viewer", authorizesOpen: false };
const event = (url, extras = {}) => ({ tabId: 7, frameId: 0, url, ...extras });

test("recognizes same-origin PDF.js viewer document references without page access", () => {
  for (const url of [
    "https://example.test/pdfjs/web/viewer.html?file=%2Ffiles%2Freport.pdf",
    "https://example.test/static/pdf.js/web/viewer.html?file=..%2F..%2Freports%2FQ1.PDF",
    "https://example.test/pdfjs-dist/web/viewer.html?file=https%3A%2F%2Fexample.test%2Freport.pdf",
    "http://example.test/pdfjs/web/viewer.html?file=document.pdf",
    "https://example.test/PDFJS/web/VIEWER.HTML?file=%2Fdocs%2Freport%2ePdF",
    "https://example.test/pdfjs/web/viewer.html?lang=en&file=%2Fdocs%2Freports.pdf%3Fdownload%3D1%23page%3D2#zoom=100"
  ]) assert.deepEqual(detectJavascriptPdfViewer(event(url)), PDF, url);
});

test("ignores arbitrary site viewer pages and query or fragment PDF hints", () => {
  for (const url of [
    "https://example.test/viewer.html?file=/report.pdf",
    "https://example.test/web/viewer.html?file=/report.pdf",
    "https://example.test/notpdfjs/web/viewer.html?file=/report.pdf",
    "https://example.test/pdfjs/web/preview.html?file=/report.pdf",
    "https://example.test/pdfjs/web/viewer.html?filename=/report.pdf",
    "https://example.test/pdfjs/web/viewer.html?file=report.txt",
    "https://example.test/pdfjs/web/viewer.html?file=/report.pdf.exe",
    "https://example.test/pdfjs/web/viewer.html?file=/preview?file=report.pdf",
    "https://example.test/pdfjs/web/viewer.html#file=report.pdf",
    "https://example.test/pdfjs/web/viewer.html?file=",
    "https://example.test/pdfjs/web/viewer.html",
    "https://example.test/document.pdf?file=other.pdf"
  ]) assert.deepEqual(detectJavascriptPdfViewer(event(url)), NONE, url);
});

test("rejects conflicting, unsupported and cross-origin file references", () => {
  for (const file of [
    "https://other.test/report.pdf",
    "//other.test/report.pdf",
    "file:///Users/private/report.pdf",
    "blob:https://example.test/report.pdf",
    "data:application/pdf,report.pdf",
    "javascript:alert(1)",
    "ftp://example.test/report.pdf",
    "https://user:pass@example.test/report.pdf",
    "/files/report%2F.pdf",
    "/files/report%5C.pdf",
    "/files/report%00.pdf",
    "/files/report%ZZ.pdf",
    " /files/report.pdf",
    "/files/report.pdf ",
    "/files/" + "a".repeat(4097) + ".pdf"
  ]) {
    const url = "https://example.test/pdfjs/web/viewer.html?file=" + encodeURIComponent(file);
    assert.deepEqual(detectJavascriptPdfViewer(event(url)), NONE, file);
  }
  for (const url of [
    "https://example.test/pdfjs/web/viewer.html?file=a.pdf&file=b.pdf",
    "https://example.test/pdfjs/web/viewer.html?file=a.pdf&file=",
    "https://user:password@example.test/pdfjs/web/viewer.html?file=a.pdf",
    "https://example.test/pdfjs%2Fweb/viewer.html?file=a.pdf",
    "https://example.test/pdfjs/web/viewer.html?file=a.pdf%0A",
    "https://example.test/pdfjs/web/viewer.html?file=a.pdf&FILE=b.pdf",
    "file:///Users/example/pdfjs/web/viewer.html?file=report.pdf",
    "https://example.test/pdfjs/web/viewer.html?file=a.pdf\n",
    "https://example.test/pdfjs/web/viewer.html?file=" + "x".repeat(8200) + ".pdf"
  ]) {
    // Case-sensitive FILE is not a PDF.js file parameter; a separate, unrelated
    // parameter does not change the one valid file reference.
    const expected = url.includes("&FILE=") ? PDF : NONE;
    assert.deepEqual(detectJavascriptPdfViewer(event(url)), expected, url);
  }
});

test("accepts only trusted top-frame browser event shapes, not DOM objects", () => {
  const url = "https://example.test/pdfjs/web/viewer.html?file=report.pdf";
  for (const extra of [
    { tabId: -1 }, { tabId: "7" }, { tabId: 1.5 },
    { tabId: Number.MAX_SAFE_INTEGER + 1 }, { frameId: 1 },
    { frameId: -1 }, { frameId: undefined }, { frameId: "0" }
  ]) assert.deepEqual(detectJavascriptPdfViewer(event(url, extra)), NONE);
  for (const record of [undefined, null, [], 1, url, new URL(url),
    { url }, Object.create(event(url))]) {
    assert.deepEqual(detectJavascriptPdfViewer(record), NONE);
  }
});

test("never invokes untrusted getters or leaks URLs in results", () => {
  const url = "https://example.test/pdfjs/web/viewer.html?file=private.pdf";
  let invoked = 0;
  const getter = event(url);
  Object.defineProperty(getter, "url", { get() {
    invoked++;
    return url;
  } });
  assert.deepEqual(detectJavascriptPdfViewer(getter), NONE);
  assert.equal(invoked, 0);
  assert.deepEqual(detectJavascriptPdfViewer(new Proxy({}, {
    getPrototypeOf() { throw Error("secret"); }
  })), NONE);

  for (const urlValue of [
    "https://example.test/pdfjs/web/viewer.html?file=secret.pdf",
    "https://example.test/pdfjs/web/viewer.html?file=not-pdf.txt"
  ]) {
    const result = detectJavascriptPdfViewer(event(urlValue));
    assert.equal(Object.isFrozen(result), true);
    assert.deepEqual(Object.keys(result).sort(),
      ["authorizesOpen", "evidence", "isPdfCandidate"]);
    assert.equal(result.authorizesOpen, false);
    assert.doesNotMatch(JSON.stringify(result), /secret|private|example|filename/i);
  }
});

test("detection is passive, does not relax permissions, and runs in CI", async () => {
  const load = (path) => readFile(new URL(path, import.meta.url), "utf8");
  const [source, background, manifestText, ci] = await Promise.all([
    load("../src/pdf-js-viewer.js"),
    load("../src/background.js"),
    load("../manifest.json"),
    load("../../../.github/workflows/ci.yml")
  ]);
  assert.match(source, /import \{ detectPdfCandidate \} from "\.\/pdf-detection\.js"/);
  for (const forbidden of [
    "addListener(", "permissions.request", "sendNativeMessage", "connectNative",
    "fetch(", "XMLHttpRequest", "WebSocket", "window.open", "downloads.open",
    "node:fs", "scan-and-open", "clamscan(", "console.", "document.", "innerHTML"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
  const manifest = JSON.parse(manifestText);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  assert.match(ci, /node --test tests\/pdf-js-viewer\.test\.mjs/);
});
