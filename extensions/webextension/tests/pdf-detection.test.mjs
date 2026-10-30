import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { detectPdfCandidate } from "../src/pdf-detection.js";

const detect = (metadata) => detectPdfCandidate(metadata);
const expected = (evidence) => ({
  isPdfCandidate: evidence !== "none", evidence, authorizesOpen: false
});

test("recognizes PDF MIME types, case and parameters without inspecting content", () => {
  for (const mimeType of ["application/pdf", "APPLICATION/PDF", " application/pdf; charset=binary ", "application/x-pdf"]) {
    assert.deepEqual(detect({ mimeType }), expected("mime-type"));
  }
  assert.deepEqual(detect({ mimeType: "application/pdf", url: "https://example.test/not-a-pdf" }),
    expected("mime-type"));
});

test("matches case-insensitive standalone .pdf suffixes in filenames and HTTP(S) URLs", () => {
  for (const filename of ["report.pdf", "report.PDF", "conference.notes.PdF"]) {
    assert.deepEqual(detect({ filename }), expected("filename"));
  }
  for (const url of [
    "https://example.test/report.pdf?download=1#page=3",
    "http://example.test/a/%72eport%2epDF?name=doc.txt",
    "file:///Users/example/Downloads/report.pdf"
  ]) assert.deepEqual(detect({ url }), expected("url-path"));
});

test("generic binary MIME can use an existing filename or URL path", () => {
  assert.deepEqual(detect({ mimeType: "application/octet-stream", filename: "receipt.PDF" }),
    expected("filename"));
  assert.deepEqual(detect({ mimeType: "binary/octet-stream", url: "https://test.invalid/document.pdf" }),
    expected("url-path"));
});

test("known non-PDF MIME vetoes misleading extension and query strings", () => {
  for (const mimeType of ["text/html", "image/png", "application/json", "application/pdf+json"]) {
    assert.deepEqual(detect({ mimeType, filename: "report.pdf", url: "https://test.invalid/report.pdf" }),
      expected("none"));
  }
  for (const metadata of [
    { filename: "report.pdf.exe" },
    { url: "https://test.invalid/report.pdf/preview?file=another.pdf" },
    { url: "https://test.invalid/view?filename=document.pdf#report.pdf" },
    { filename: ".pdf" }, { filename: "path/report.pdf" },
    { url: "data:application/pdf,content" },
    { url: "blob:https://test.invalid/id.pdf" },
    { url: "javascript:alert('report.pdf')" },
    { url: "https://test.invalid/report%00.pdf" },
    { url: "https://test.invalid/report%ZZ.pdf" }
  ]) assert.deepEqual(detect(metadata), expected("none"));
});

test("invalid or oversized inputs fail closed without executing property getters", () => {
  const getter = {};
  Object.defineProperty(getter, "url", { get() { throw Error("getter must not run"); } });
  for (const input of [undefined, null, 1, "report.pdf", [], new URL("https://test.invalid/file.pdf"),
    getter, { url: "https://test.invalid/a.pdf", allowOpen: true },
    { url: "a".repeat(8193) }, { filename: "a".repeat(513) + ".pdf" },
    { url: Symbol("pdf") }, { mimeType: 1 }, { url: "https://test.invalid/a.pdf", filename: null }]) {
    assert.deepEqual(detect(input), expected("none"));
  }
});

test("returns only path-free immutable candidate metadata and never authorizes opening", () => {
  for (const metadata of [
    { url: "https://private.example.test/secret.pdf?token=private" },
    { filename: "private-document.pdf" }, { mimeType: "application/pdf" }, {}]) {
    const result = detect(metadata);
    assert.equal(Object.isFrozen(result), true);
    assert.deepEqual(Object.keys(result).sort(), ["authorizesOpen", "evidence", "isPdfCandidate"]);
    assert.equal(result.authorizesOpen, false);
    assert.equal(JSON.stringify(result).includes("private"), false);
  }
});

test("the shared module has no browser, native transport, filesystem or network side effects", async () => {
  const source = await readFile(new URL("../src/pdf-detection.js", import.meta.url), "utf8");
  for (const forbidden of [
    "chrome.", "browser.", "addListener", "sendNativeMessage", "connectNative",
    "fetch(", "XMLHttpRequest", "WebSocket", "window.open", "file_launcher",
    "scan-and-open", "node:fs", "ClamAV", "localStorage"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
