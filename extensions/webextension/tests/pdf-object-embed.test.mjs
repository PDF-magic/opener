import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { detectPdfObjectEmbed as detect } from "../src/pdf-object-embed.js";

const none = { isPdfCandidate: false, evidence: "none", authorizesOpen: false };
const candidate = (evidence) => ({
  isPdfCandidate: true, evidence, authorizesOpen: false
});
const object = (data, extras = {}) => ({ tagName: "OBJECT", data, ...extras });

test("identifies typed PDF objects, including extensionless and relative data URLs", () => {
  for (const data of [
    "report.pdf", "../documents/report", "/download?id=42",
    "https://example.test/download", "file:///Users/example/statement"
  ]) {
    assert.deepEqual(detect(object(data, { type: "application/pdf" })), candidate("object-type"));
    assert.deepEqual(detect(object(data, { type: "APPLICATION/X-PDF; charset=UTF-8" })),
      candidate("object-type"));
  }
  assert.deepEqual(detect({ tagName: "object", data: "report.pdf", type: "application/pdf" }),
    candidate("object-type"));
});

test("identifies PDF-suffixed object data without a declared type", () => {
  for (const data of [
    "report.pdf", "../reports/quarterly.PDF", "/docs/report.pdf?download=1#page=2",
    "https://example.test/a/%72eport%2ePdF?x=1",
    "//example.test/report.pdf", "file:///Users/example/Documents/report.pdf"
  ]) assert.deepEqual(detect(object(data)), candidate("object-data"), data);
});

test("non-object elements and explicit non-PDF types are never misidentified", () => {
  for (const tagName of ["embed", "iframe", "img", "OBJECTS", "div", ""])
    assert.deepEqual(detect({ tagName, data: "report.pdf", type: "application/pdf" }), none);
  for (const type of ["text/html", "image/png", "application/octet-stream",
    "application/pdf+json", "application/json", "application/pdf; invalid"])
    assert.deepEqual(detect(object("/report.pdf", { type })), none, type);
  for (const data of ["", "/reports/statement.txt", "/view?file=report.pdf",
    "https://example.test/report.pdf/preview", "report.pdf.exe", "#report.pdf",
    "?file=report.pdf", ".pdf"])
    assert.deepEqual(detect(object(data)), none, data);
});

test("rejects unsupported data schemes, credentials, malformed and encoded paths", () => {
  for (const data of [
    "data:application/pdf,JVBERi0x", "blob:https://example.test/id",
    "javascript:alert(1)", "ftp://example.test/report.pdf",
    "chrome-extension://invalid/report.pdf", "https://user:pass@example.test/report.pdf",
    "http://example.test/report%ZZ.pdf", "/report%00.pdf", "/report%2Ffake.pdf",
    "/report%5Cfake.pdf", " report.pdf", "report.pdf ", "report.pdf\n",
    "C:\\Reports\\report.pdf", "a".repeat(8193) + ".pdf"
  ]) {
    assert.deepEqual(detect(object(data)), none, data);
    assert.deepEqual(detect(object(data, { type: "application/pdf" })), none, data);
  }
});

test("rejects missing attributes, unexpected page content, getters and proxies", () => {
  let getterCalls = 0;
  const getter = object("report.pdf");
  Object.defineProperty(getter, "type", { get() {
    getterCalls++;
    return "application/pdf";
  } });
  for (const input of [
    null, undefined, [], new Date(), "<object data='report.pdf'>", 0,
    { tagName: "object", type: "application/pdf" },
    { tagName: "object", data: "" },
    object("report.pdf", { innerHTML: "private" }),
    object("report.pdf", { src: "report.pdf" }),
    object("report.pdf", { type: null }),
    object("report.pdf", { type: "" }), getter,
    Object.create(object("report.pdf")),
    new Proxy(object("report.pdf"), { getPrototypeOf() { throw Error("private"); } })
  ]) assert.deepEqual(detect(input), none);
  assert.equal(getterCalls, 0);
  const withSymbol = object("report.pdf");
  withSymbol[Symbol("private")] = "secret";
  assert.deepEqual(detect(withSymbol), none);
});

test("returns immutable evidence only, without URLs, contents or opening authority", () => {
  for (const attrs of [
    object("https://private.example/secret.pdf"),
    object("https://private.example/download?token=secret", { type: "application/pdf" }),
    object("/private/secret.txt"),
  ]) {
    const result = detect(attrs);
    assert.equal(Object.isFrozen(result), true);
    assert.deepEqual(Object.keys(result).sort(),
      ["authorizesOpen", "evidence", "isPdfCandidate"]);
    assert.equal(result.authorizesOpen, false);
    assert.doesNotMatch(JSON.stringify(result), /private|secret|token/);
  }
});

test("remains passive, permission-free and covered by existing required CI discovery", async () => {
  const read = (path) => readFile(new URL(path, import.meta.url), "utf8");
  const [source, ci, packageText, manifestText, background] = await Promise.all([
    read("../src/pdf-object-embed.js"),
    read("../../../.github/workflows/ci.yml"),
    read("../package.json"),
    read("../manifest.json"),
    read("../src/background.js")
  ]);
  assert.match(ci, /\bnpm test\b/);
  const pkg = JSON.parse(packageText);
  assert.match(pkg.scripts.test, /tests\/\*\.test\.mjs/);
  const manifest = JSON.parse(manifestText);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.equal(manifest.content_scripts, undefined);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  for (const forbidden of [
    "querySelector(", "getAttribute(", "innerHTML", "outerHTML", "document.",
    "chrome.", "browser.", "addListener(", "permissions.request",
    "sendNativeMessage(", "connectNative(", "fetch(", "XMLHttpRequest",
    "WebSocket", "window.open(", "downloads.open(", "scan-and-open",
    "node:fs", "console."
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
