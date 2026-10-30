import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { detectPdfEmbedElement } from "../src/pdf-embed-element.js";

const none = { isPdfCandidate: false, evidence: "none", authorizesOpen: false };
const match = (evidence) => ({ isPdfCandidate: true, evidence, authorizesOpen: false });
const embed = (src, extra = {}) => detectPdfEmbedElement({ tagName: "EMBED", src, ...extra });

test("recognizes PDF <embed> type and src evidence without reading page HTML", () => {
  for (const type of ["application/pdf", "APPLICATION/PDF", "application/x-pdf", " application/pdf; charset=utf-8 "]) {
    assert.deepEqual(embed("https://example.test/view?id=1", { type }), match("embed-type"));
  }
  for (const src of [
    "https://example.test/report.pdf", "http://example.test/REPORT.PDF?download=1#page=3",
    "https://example.test/%72eport%2ePdf", "https://example.test/dir/report.pdf"
  ]) assert.deepEqual(embed(src), match("embed-src"), src);
  assert.deepEqual(embed("https://example.test/a.pdf", { type: "application/pdf" }), match("embed-type"));
});

test("resolves relative <embed src> values only against an explicit valid page base", () => {
  for (const src of ["../docs/report.PDF", "/docs/report.pdf", "//cdn.example.test/report.pdf"]) {
    assert.deepEqual(embed(src, { baseUrl: "https://example.test/private/page.html" }), match("embed-src"));
  }
  assert.deepEqual(embed("report.pdf"), none);
  assert.deepEqual(embed("report.pdf", { baseUrl: "file:///private/index.html" }), none);
  assert.deepEqual(embed("report.pdf", { baseUrl: "https://user:pass@example.test/page.html" }), none);
});

test("non-embed elements, misleading types and non-PDF paths do not qualify", () => {
  for (const tagName of ["object", "iframe", "img", "video", "embedder", "", 123]) {
    assert.deepEqual(detectPdfEmbedElement({ tagName, src: "https://example.test/a.pdf", type: "application/pdf" }), none);
  }
  for (const type of ["text/html", "image/svg+xml", "application/json", "application/pdf+json"]) {
    assert.deepEqual(embed("https://example.test/report.pdf", { type }), none);
  }
  for (const src of [
    "https://example.test/preview?file=report.pdf", "https://example.test/document.pdf.exe",
    "https://example.test/a.pdf/preview", "https://example.test/.pdf",
    "https://example.test/%2F.pdf", "https://example.test/%5c.pdf",
    "https://example.test/%00.pdf", "https://example.test/%ZZ.pdf"
  ]) assert.deepEqual(embed(src), none, src);
});

test("dangerous, credentialed, and malformed embedded sources fail closed even with PDF type", () => {
  for (const src of [
    "data:application/pdf;base64,AA", "blob:https://example.test/uuid",
    "javascript:alert(1)", "file:///private/report.pdf",
    "ftp://example.test/report.pdf", "https://user:secret@example.test/report.pdf",
    "https://example.test/a\\report.pdf", " https://example.test/a.pdf",
    "https://example.test/a.pdf\n", "https://example.test/a%0A.pdf",
    "https://example.test/%2F.pdf", ""
  ]) assert.deepEqual(embed(src, { type: "application/pdf" }), none, src);
});

test("invalid records and accessors cannot introduce page data or execute getters", () => {
  const hostile = { tagName: "embed", src: "https://example.test/report.pdf" };
  Object.defineProperty(hostile, "src", { get() { throw Error("do not execute"); } });
  const inherited = Object.create({ tagName: "embed" });
  inherited.src = "https://example.test/report.pdf";
  const symbol = { tagName: "embed", src: "https://example.test/report.pdf" };
  symbol[Symbol("private")] = "secret";
  for (const item of [null, undefined, 1, [], hostile, inherited, symbol,
    { tagName: "embed" }, { tagName: "embed", src: 1 },
    { tagName: "embed", src: "https://example.test/a.pdf", pageHtml: "secret" },
    { tagName: "embed", src: "https://example.test/a.pdf", type: 2 },
    { tagName: "embed", src: "a".repeat(8193) },
    { tagName: "embed", src: "https://example.test/a.pdf", type: "a".repeat(257) },
    new Proxy({}, { getPrototypeOf() { throw Error("do not execute"); } })]) {
    assert.deepEqual(detectPdfEmbedElement(item), none);
  }
});

test("candidate records contain no URLs, page values or scan/open authorization", () => {
  for (const details of [
    { tagName: "embed", src: "https://example.test/private.pdf?token=secret" },
    { tagName: "embed", src: "https://example.test/view?private=1", type: "application/pdf" },
    { tagName: "embed", src: "https://example.test/view", type: "text/html" }
  ]) {
    const result = detectPdfEmbedElement(details);
    assert.equal(Object.isFrozen(result), true);
    assert.deepEqual(Object.keys(result).sort(), ["authorizesOpen", "evidence", "isPdfCandidate"]);
    assert.equal(result.authorizesOpen, false);
    assert.doesNotMatch(JSON.stringify(result), /private|secret|token|example/);
  }
});

test("embed detection stays passive without content scripts or opening bypasses", async () => {
  const source = await readFile(new URL("../src/pdf-embed-element.js", import.meta.url), "utf8");
  for (const forbidden of [
    "document.", "querySelector(", "getAttribute(", "innerHTML", "outerHTML",
    "chrome.", "browser.", "addListener(", "fetch(", "XMLHttpRequest", "WebSocket",
    "sendNativeMessage(", "connectNative(", "window.open(", "node:fs", "console."
  ]) assert.equal(source.includes(forbidden), false, forbidden);
  const background = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  const manifest = JSON.parse(await readFile(new URL("../manifest.json", import.meta.url), "utf8"));
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.permissions, []);
  assert.equal(Object.hasOwn(manifest, "content_scripts"), false);
});
