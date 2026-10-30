import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { detectExtensionlessPdfResponse } from "../src/pdf-extensionless.js";

const NONE = { isPdfCandidate: false, evidence: "none", authorizesOpen: false };
const PDF = { isPdfCandidate: true, evidence: "mime-type", authorizesOpen: false };
const event = (url, extras = {}) => ({
  url, tabId: 7, frameId: 0, type: "main_frame", ...extras
});
const header = (value) => [{ name: "Content-Type", value }];

test("identifies actual extensionless PDF response URLs from trusted MIME evidence", () => {
  for (const url of [
    "https://example.test/download",
    "https://example.test/download?id=42",
    "https://example.test/reports/12345#page=2",
    "https://example.test/files/report.bin",
    "http://example.test/statement",
    "https://example.test/",
    "https://example.test/document.pdf/preview"
  ]) {
    assert.deepEqual(detectExtensionlessPdfResponse(
      event(url, { responseHeaders: header("application/pdf") })
    ), PDF, url);
    assert.deepEqual(detectExtensionlessPdfResponse(
      event(url, { mimeType: "application/x-pdf; charset=UTF-8" })
    ), PDF, url);
  }
});

test("does not redefine an ordinary .pdf URL as extensionless", () => {
  for (const url of [
    "https://example.test/report.pdf",
    "https://example.test/report.PDF?download=1",
    "https://example.test/report%2ePdF#page=2",
    "https://example.test/files/%72eport.pdf"
  ]) {
    assert.deepEqual(detectExtensionlessPdfResponse(
      event(url, { responseHeaders: header("application/pdf") })
    ), NONE, url);
  }
});

test("extensionless URLs and misleading filename hints never replace MIME evidence", () => {
  for (const extras of [
    {},
    { responseHeaders: [] },
    { mimeType: "application/octet-stream" },
    { mimeType: "text/html" },
    { mimeType: "application/pdf+json" },
    { filename: "report.pdf" },
    { mimeType: "text/plain", filename: "report.pdf" },
    { responseHeaders: header("image/png"), filename: "report.pdf" },
    { mimeType: "application/pdf", responseHeaders: header("text/html") },
    { responseHeaders: [...header("application/pdf"), ...header("application/pdf")] },
    { responseHeaders: header("application/pdf\nX-Secret: a") },
    { responseHeaders: [{ name: "Content-Type", value: 42 }] }
  ]) {
    assert.deepEqual(detectExtensionlessPdfResponse(
      event("https://example.test/download?id=report.pdf", extras)
    ), NONE);
  }
});

test("rejects unsupported, credential-bearing or ambiguous URL schemes and encodings", () => {
  for (const url of [
    "file:///Users/example/report",
    "ftp://example.test/download",
    "data:application/pdf,content",
    "blob:https://example.test/download",
    "javascript:alert(1)",
    "chrome-extension://example/download",
    "https://user:pass@example.test/download",
    "https://example.test/file%2Fpart",
    "https://example.test/file%5Cpart",
    "https://example.test/file%00part",
    "https://example.test/file%ZZ",
    "https://example.test/file%0Apart",
    "https://example.test/file\npart",
    "https://example.test/" + "a".repeat(8193),
    "/download?id=1",
    "not-a-url"
  ]) {
    assert.deepEqual(detectExtensionlessPdfResponse(
      event(url, { responseHeaders: header("application/pdf") })
    ), NONE, url);
  }
});

test("invalid or subframe navigation events cannot claim an extensionless PDF", () => {
  for (const patch of [
    { frameId: 1 }, { frameId: -1 }, { frameId: "0" },
    { frameId: undefined }, { tabId: -1 }, { tabId: null },
    { tabId: 3.5 }, { tabId: "7" }, { tabId: Number.MAX_SAFE_INTEGER + 1 },
    { type: "sub_frame" }, { type: "xmlhttprequest" }, { type: undefined }
  ]) {
    assert.deepEqual(detectExtensionlessPdfResponse(event(
      "https://example.test/download",
      { responseHeaders: header("application/pdf"), ...patch }
    )), NONE);
  }
  for (const record of [null, undefined, 5, "pdf", [], new Date()]) {
    assert.deepEqual(detectExtensionlessPdfResponse(record), NONE);
  }
});

test("hostile fields and proxy traps cannot execute URL getters or leak metadata", () => {
  let invoked = 0;
  const eventWithGetter = event("https://example.test/download", {
    mimeType: "application/pdf"
  });
  Object.defineProperty(eventWithGetter, "url", { get() {
    invoked++;
    return "https://example.test/download";
  } });
  assert.deepEqual(detectExtensionlessPdfResponse(eventWithGetter), NONE);
  assert.equal(invoked, 0);
  const inherited = Object.create(event("https://example.test/download", {
    mimeType: "application/pdf"
  }));
  assert.deepEqual(detectExtensionlessPdfResponse(inherited), NONE);
  const hostile = new Proxy({}, { getPrototypeOf() { throw Error("private"); } });
  assert.deepEqual(detectExtensionlessPdfResponse(hostile), NONE);
});

test("results are immutable and never contain URLs, filenames or opening permissions", () => {
  for (const details of [
    event("https://example.test/download?private=secret", {
      responseHeaders: header("application/pdf")
    }),
    event("https://example.test/download?private=secret", {
      mimeType: "application/pdf", filename: "private.pdf"
    }),
    event("https://example.test/download?private=secret")
  ]) {
    const result = detectExtensionlessPdfResponse(details);
    assert.equal(Object.isFrozen(result), true);
    assert.deepEqual(Object.keys(result).sort(),
      ["authorizesOpen", "evidence", "isPdfCandidate"]);
    assert.equal(result.authorizesOpen, false);
    assert.equal(JSON.stringify(result).includes("private"), false);
    assert.equal(JSON.stringify(result).includes("secret"), false);
  }
});

test("reuses existing classifiers, remains passive, and is executed by required CI", async () => {
  const read = async (path) => readFile(new URL(path, import.meta.url), "utf8");
  const [source, ci, manifestText, background] = await Promise.all([
    read("../src/pdf-extensionless.js"),
    read("../../../.github/workflows/ci.yml"),
    read("../manifest.json"),
    read("../src/background.js")
  ]);
  assert.match(source, /import \{ detectPdfResponseMime \} from "\.\/pdf-response-mime\.js"/);
  assert.match(source, /import \{ detectPdfNavigation \} from "\.\/pdf-navigation\.js"/);
  assert.match(ci, /node --test tests\/pdf-extensionless\.test\.mjs/);
  const manifest = JSON.parse(manifestText);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  for (const forbidden of [
    "addListener(", "permissions.request", "sendNativeMessage(", "connectNative(",
    "fetch(", "XMLHttpRequest", "WebSocket", "window.open", "downloads.open",
    "scan-and-open", "node:fs", "clamscan(", "console."
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
