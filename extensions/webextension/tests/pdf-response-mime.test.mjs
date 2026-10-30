import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { detectPdfResponseMime as detect } from "../src/pdf-response-mime.js";

const none = Object.freeze({
  isPdfCandidate: false, evidence: "none", authorizesOpen: false
});
const yes = Object.freeze({
  isPdfCandidate: true, evidence: "mime-type", authorizesOpen: false
});
const response = (metadata = {}) =>
  detect({ tabId: 11, frameId: 0, type: "main_frame", ...metadata });
const contentType = (value) => [{ name: "Content-Type", value }];

test("detects a PDF from main-frame response headers only when exposed", () => {
  for (const mime of ["application/pdf", "APPLICATION/PDF",
    "application/x-pdf", "Application/X-PDF; charset=UTF-8",
    'application/pdf; charset="binary"']) {
    assert.deepEqual(response({ responseHeaders: contentType(mime) }), yes);
    assert.deepEqual(response({ mimeType: mime }), yes);
  }
  assert.deepEqual(response({
    responseHeaders: [{ name: "Server", value: "private" },
      { name: "content-type", value: "application/pdf; charset=UTF-8" }]
  }), yes);
  assert.deepEqual(response({
    mimeType: "application/pdf", responseHeaders: contentType("APPLICATION/PDF; charset=UTF-8")
  }), yes);
});

test("unsupported or omitted MIME metadata never becomes a PDF claim", () => {
  for (const meta of [{}, { responseHeaders: [] },
    { responseHeaders: [{ name: "X-Mime", value: "application/pdf" }] },
    { mimeType: "text/html" }, { mimeType: "application/octet-stream" },
    { mimeType: "application/pdf+json" },
    { mimeType: "text/html", url: "https://private.test/report.pdf" },
    { responseHeaders: contentType("image/png"), filename: "report.pdf" },
    { responseHeaders: [{ name: "Content-Type", binaryValue: [1, 2] }] }]) {
    assert.deepEqual(response(meta), none);
  }
});

test("rejects conflicting, repeated, malformed and unsupported headers", () => {
  for (const meta of [
    { mimeType: "text/html", responseHeaders: contentType("application/pdf") },
    { mimeType: "application/pdf", responseHeaders: contentType("text/plain") },
    { responseHeaders: [...contentType("application/pdf"), ...contentType("application/pdf")] },
    { responseHeaders: contentType("application/pdf\nX-Secret: abc") },
    { responseHeaders: contentType("application/pdf; broken") },
    { responseHeaders: contentType("application/pdf; charset=UTF-8\r") },
    { responseHeaders: [{ name: "Content-Type", value: 123 }] },
    { responseHeaders: null }, { responseHeaders: "application/pdf" },
    { responseHeaders: Array(3) },
    { responseHeaders: Array.from({ length: 129 }, () => ({ name: "Other" })) },
    { mimeType: "application/pdf\n" }, { mimeType: null }, { mimeType: 123 }
  ]) assert.deepEqual(response(meta), none);
});

test("requires trusted top-frame browser event context, not page data", () => {
  for (const context of [
    { type: "sub_frame" }, { frameId: 1 }, { frameId: -1 },
    { tabId: -1 }, { tabId: 1.5 }, { tabId: "11" },
    { tabId: Number.MAX_SAFE_INTEGER + 1 }, { type: "xmlhttprequest" },
    { type: "main_frame", frameId: null }, { type: undefined }
  ]) {
    assert.deepEqual(detect({
      tabId: 11, frameId: 0, type: "main_frame",
      responseHeaders: contentType("application/pdf"), ...context
    }), none);
  }
  for (const event of [undefined, null, "", 0, [], new Date(),
    { mimeType: "application/pdf" }, { type: "main_frame", frameId: 0 }]) {
    assert.deepEqual(detect(event), none);
  }
});

test("does not execute getters or leak metadata from hostile browser objects", () => {
  let invoked = 0;
  const badHeader = { name: "Content-Type" };
  Object.defineProperty(badHeader, "value", { get() { invoked++; return "application/pdf"; } });
  assert.deepEqual(response({ responseHeaders: [badHeader] }), none);
  const badEvent = { type: "main_frame", tabId: 11, frameId: 0 };
  Object.defineProperty(badEvent, "mimeType", { get() { invoked++; return "application/pdf"; } });
  assert.deepEqual(detect(badEvent), none);
  const proxy = new Proxy({ type: "main_frame", tabId: 11, frameId: 0 }, {
    getPrototypeOf() { throw Error("secret event contents"); }
  });
  assert.deepEqual(detect(proxy), none);
  assert.equal(invoked, 0);
});

test("returns only immutable, path-free evidence and never a scan or open grant", () => {
  for (const meta of [{ mimeType: "application/pdf", url: "https://private.invalid/secret.pdf" },
    { mimeType: "text/plain", filename: "/private/statement.pdf" }, {}]) {
    const result = response(meta);
    assert.equal(Object.isFrozen(result), true);
    assert.deepEqual(Object.keys(result).sort(),
      ["authorizesOpen", "evidence", "isPdfCandidate"]);
    assert.equal(result.authorizesOpen, false);
    assert.equal(JSON.stringify(result).includes("private"), false);
  }
});

test("background remains inert and this classifier requires no new privileges", async () => {
  const [source, background, manifest] = await Promise.all([
    readFile(new URL("../src/pdf-response-mime.js", import.meta.url), "utf8"),
    readFile(new URL("../src/background.js", import.meta.url), "utf8"),
    readFile(new URL("../manifest.json", import.meta.url), "utf8")
  ]);
  assert.equal(background.trim(), "// Inactive shared WebExtensions background entry point.\n// Do not listen for messages, inspect PDFs or request native access here.\nvoid 0;");
  const permissions = JSON.parse(manifest);
  assert.deepEqual(permissions.permissions, []);
  assert.deepEqual(permissions.host_permissions, []);
  for (const forbidden of ["addListener(", "sendNativeMessage(", "connectNative(",
    "fetch(", "XMLHttpRequest", "window.open(", "requestPermission(", "downloads.open(",
    "scan-and-open", "clamscan("]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});
