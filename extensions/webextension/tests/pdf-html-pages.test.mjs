import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  classifyHtmlOrPdfResponse as classify,
  detectPdfResponseMime
} from "../src/pdf-response-mime.js";

const NONE = Object.freeze({
  isHtmlPage: false, isPdfCandidate: false,
  evidence: "none", authorizesOpen: false
});
const HTML = Object.freeze({
  isHtmlPage: true, isPdfCandidate: false,
  evidence: "html-mime-type", authorizesOpen: false
});
const PDF = Object.freeze({
  isHtmlPage: false, isPdfCandidate: true,
  evidence: "mime-type", authorizesOpen: false
});
const event = (extras = {}) => ({
  tabId: 7, frameId: 0, type: "main_frame", ...extras
});
const headers = (mime) => [{ name: "Content-Type", value: mime }];
const misleading = {
  url: "https://private.example.test/statement.pdf?document=secret.pdf",
  filename: "report.pdf"
};

test("known HTML document MIME overrides .pdf URLs, filenames and download hints", () => {
  for (const mime of [
    "text/html", "TEXT/HTML", "text/html; charset=utf-8",
    'text/html; charset="UTF-8"', "application/xhtml+xml",
    "APPLICATION/XHTML+XML; charset=UTF-8"
  ]) {
    assert.deepEqual(classify(event({ ...misleading, mimeType: mime })), HTML, mime);
    assert.deepEqual(classify(event({
      ...misleading, responseHeaders: headers(mime),
      contentDisposition: 'attachment; filename="report.pdf"'
    })), HTML, mime);
    assert.deepEqual(detectPdfResponseMime(event({
      ...misleading, responseHeaders: headers(mime)
    })), { isPdfCandidate: false, evidence: "none", authorizesOpen: false });
  }
});

test("a validated PDF response remains a candidate without granting opening", () => {
  for (const mime of [
    "application/pdf", "APPLICATION/PDF; charset=binary",
    "application/x-pdf"
  ]) {
    assert.deepEqual(classify(event({ mimeType: mime })), PDF);
    assert.deepEqual(classify(event({ responseHeaders: headers(mime) })), PDF);
    assert.deepEqual(classify(event({
      mimeType: mime, responseHeaders: headers(mime)
    })), PDF);
  }
});

test("HTML-looking URLs are not proof of HTML and PDF-looking URLs are not proof of PDF", () => {
  for (const input of [
    { ...misleading }, { ...misleading, responseHeaders: [] },
    { ...misleading, mimeType: "application/octet-stream" },
    { url: "https://example.test/index.html" },
    { url: "https://example.test/report.pdf", mimeType: "text/plain" },
    { ...misleading, mimeType: "application/json" },
    { ...misleading, mimeType: "application/pdf+json" }
  ]) assert.deepEqual(classify(event(input)), NONE);
  // The trusted response MIME (not the URL suffix) decides classification.
  assert.deepEqual(classify(event({
    url: "https://example.test/index.html", mimeType: "application/pdf"
  })), PDF);
});

test("ambiguous or malformed browser Content-Type declarations fail closed", () => {
  for (const input of [
    { mimeType: "application/pdf", responseHeaders: headers("text/html") },
    { mimeType: "text/html", responseHeaders: headers("application/pdf") },
    { mimeType: "text/html", responseHeaders: headers("application/xhtml+xml") },
    { responseHeaders: [...headers("text/html"), ...headers("text/html")] },
    { responseHeaders: [...headers("text/html"), ...headers("application/pdf")] },
    { responseHeaders: headers("text/html\nX-Secret: private") },
    { responseHeaders: headers("text/html; invalid") },
    { responseHeaders: [{ name: "Content-Type", binaryValue: [1, 2] }] },
    { responseHeaders: Array(2) }, { responseHeaders: null },
    { mimeType: null }, { mimeType: 42 },
    { mimeType: "text/html; charset=bad\nX:yes" }
  ]) assert.deepEqual(classify(event({ ...misleading, ...input })), NONE);
});

test("subframe and untrusted context cannot assert main-frame HTML or PDF", () => {
  for (const patch of [
    { type: "sub_frame" }, { type: "xmlhttprequest" },
    { type: undefined }, { frameId: 2 }, { frameId: -1 },
    { frameId: "0" }, { frameId: undefined },
    { tabId: -1 }, { tabId: "7" }, { tabId: 2.5 },
    { tabId: Number.MAX_SAFE_INTEGER + 1 }
  ]) for (const mime of ["text/html", "application/pdf"]) {
    assert.deepEqual(classify(event({ mimeType: mime, ...patch })), NONE);
  }
  for (const invalid of [null, undefined, [], new Date(), "text/html", 7]) {
    assert.deepEqual(classify(invalid), NONE);
  }
});

test("hostile metadata accessors and sparse/accessor header arrays are never evaluated", () => {
  let touched = 0;
  const eventWithGetter = event();
  Object.defineProperty(eventWithGetter, "mimeType", {
    get() { touched++; return "text/html"; }
  });
  const headersWithGetter = [];
  Object.defineProperty(headersWithGetter, "0", {
    get() { touched++; return { name: "Content-Type", value: "text/html" }; }
  });
  headersWithGetter.length = 1;
  const headerWithGetter = { name: "Content-Type" };
  Object.defineProperty(headerWithGetter, "value", {
    get() { touched++; return "text/html"; }
  });
  for (const metadata of [
    eventWithGetter,
    event({ responseHeaders: headersWithGetter }),
    event({ responseHeaders: [headerWithGetter] }),
    new Proxy({}, { getPrototypeOf() { throw Error("secret"); } })
  ]) {
    assert.deepEqual(classify(metadata), NONE);
  }
  assert.equal(touched, 0);
});

test("results contain only frozen, privacy-safe flags and scanner remains inert", async () => {
  const load = (p) => readFile(new URL(p, import.meta.url), "utf8");
  const [source, manifestText, background, ci] = await Promise.all([
    load("../src/pdf-response-mime.js"),
    load("../manifest.json"), load("../src/background.js"),
    load("../../../.github/workflows/ci.yml")
  ]);
  const manifest = JSON.parse(manifestText);
  for (const result of [
    classify(event({ ...misleading, mimeType: "text/html" })),
    classify(event({ ...misleading, mimeType: "application/pdf" })),
    classify(event({ ...misleading }))
  ]) {
    assert.equal(Object.isFrozen(result), true);
    assert.deepEqual(Object.keys(result).sort(),
      ["authorizesOpen", "evidence", "isHtmlPage", "isPdfCandidate"]);
    assert.equal(result.authorizesOpen, false);
    assert.doesNotMatch(JSON.stringify(result), /secret|private|report\.pdf/);
  }
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  assert.match(ci, /node --test tests\/pdf-html-pages\.test\.mjs/);
  for (const forbidden of [
    "addListener(", "permissions.request", "connectNative(", "sendNativeMessage(",
    "fetch(", "XMLHttpRequest", "WebSocket", "window.open(", "downloads.open(",
    "node:fs", "ClamAV", "scan-and-open", "console."
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
