import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { classifyPdfDownloadMetadata } from "../src/page-content-boundary.js";
import { normalizeDownloadEvent } from "../src/download-monitoring.js";

const root = fileURLToPath(new URL("../", import.meta.url));
const none = { isPdfCandidate: false, evidence: "none", authorizesOpen: false };
const candidate = (evidence) => ({
  isPdfCandidate: true, evidence, authorizesOpen: false
});
const incoming = (extras = {}) => ({ kind: "created", id: 18, ...extras });

test("only normalized download metadata reaches PDF candidate detection", () => {
  const normalized = normalizeDownloadEvent("created", {
    id: 18, mime: "application/pdf", filename: "/Users/example/private.pdf",
    url: "https://private.example/search?q=secret", pageHtml: "<h1>secret</h1>",
    cookies: "private=1", referrer: "https://private.example/"
  });
  assert.deepEqual(classifyPdfDownloadMetadata(normalized), candidate("mime-type"));
  assert.deepEqual(classifyPdfDownloadMetadata(normalizeDownloadEvent("created", {
    id: 20, filename: "C:\\Private\\document.PDF"
  })), candidate("filename"));
});

test("known non-PDF types veto misleading PDF-looking filenames", () => {
  for (const mime of ["text/html", "text/plain", "image/png", "application/json"]) {
    assert.deepEqual(classifyPdfDownloadMetadata(incoming({
      mime, filename: "/Downloads/preview.pdf"
    })), none);
  }
  assert.deepEqual(classifyPdfDownloadMetadata(incoming({ filename: "report.pdf.exe" })), none);
  assert.deepEqual(classifyPdfDownloadMetadata(incoming({ filename: "not-a-pdf.txt" })), none);
});

test("never accept raw browser events with URLs, page contents, or other unknown fields", () => {
  const original = incoming({ mime: "application/pdf", filename: "report.pdf" });
  for (const extra of [
    { url: "https://private.example/report.pdf" },
    { pageText: "secret browsing activity" },
    { html: "<main>private page</main>" },
    { body: "private body content" },
    { dom: { innerHTML: "secret" } },
    { tabId: 42 },
    { headers: { authorization: "private" } },
    { cookies: "private=1" },
    { content: "document bytes" }
  ]) assert.deepEqual(classifyPdfDownloadMetadata({ ...original, ...extra }), none);
});

test("page-derived objects, non-download events, and invalid identifiers fail closed", () => {
  for (const item of [
    null, undefined, [], 1, "application/pdf",
    new URL("https://example.invalid/document.pdf"),
    { mime: "application/pdf", filename: "report.pdf" },
    incoming({ kind: "erased", mime: "application/pdf" }),
    incoming({ kind: "navigation", mime: "application/pdf" }),
    incoming({ id: -1, mime: "application/pdf" }),
    incoming({ id: "18", mime: "application/pdf" }),
    incoming({ id: Number.MAX_SAFE_INTEGER + 1, mime: "application/pdf" }),
    incoming({ filename: "bad\0report.pdf" }),
    incoming({ mime: 7, filename: "report.pdf" }),
    incoming({ filename: "x".repeat(4097) + ".pdf" })
  ]) assert.deepEqual(classifyPdfDownloadMetadata(item), none);
});

test("does not execute hostile or unrelated property getters", () => {
  const unsafe = incoming({ mime: "application/pdf" });
  Object.defineProperty(unsafe, "pageHtml", {
    enumerable: true, get() { throw new Error("page contents accessed"); }
  });
  assert.deepEqual(classifyPdfDownloadMetadata(unsafe), none);

  const metadataGetter = incoming();
  Object.defineProperty(metadataGetter, "mime", {
    enumerable: true, get() { throw new Error("metadata getter accessed"); }
  });
  assert.deepEqual(classifyPdfDownloadMetadata(metadataGetter), none);

  const inherited = Object.create({ kind: "created", id: 1 });
  inherited.mime = "application/pdf";
  assert.deepEqual(classifyPdfDownloadMetadata(inherited), none);

  const withSymbol = incoming({ mime: "application/pdf" });
  withSymbol[Symbol("private")] = "private content";
  assert.deepEqual(classifyPdfDownloadMetadata(withSymbol), none);
});

test("does not read page text even for a PDF-labeled download", () => {
  let reads = 0;
  const safe = incoming({ mime: "application/pdf", filename: "safe.pdf" });
  const proxy = new Proxy(safe, {
    get(target, key, receiver) {
      reads += 1;
      return Reflect.get(target, key, receiver);
    }
  });
  assert.deepEqual(classifyPdfDownloadMetadata(proxy), candidate("mime-type"));
  assert.equal(reads, 0);
});

test("recognizes only the basename and never leaks a downloaded filename or path", () => {
  for (const path of [
    "/Users/private/Documents/sensitive.pdf",
    "C:\\Users\\Private\\Documents\\sensitive.PDF",
    "file.pdf"
  ]) {
    const result = classifyPdfDownloadMetadata(incoming({ filename: path }));
    assert.deepEqual(result, candidate("filename"));
    assert.equal(JSON.stringify(result).includes("private"), false);
    assert.equal(JSON.stringify(result).includes("sensitive"), false);
    assert.equal(Object.isFrozen(result), true);
  }
});

test("non-PDF events emit only inert, immutable, minimal results", () => {
  const result = classifyPdfDownloadMetadata(incoming({ mime: "text/html" }));
  assert.deepEqual(result, none);
  assert.deepEqual(Object.keys(result).sort(), ["authorizesOpen", "evidence", "isPdfCandidate"]);
  assert.equal(Object.isFrozen(result), true);
  assert.throws(() => { result.authorizesOpen = true; }, TypeError);
});

test("download erase notifications are not a reason to collect any content", () => {
  const erased = normalizeDownloadEvent("erased", 123);
  assert.deepEqual(classifyPdfDownloadMetadata(erased), none);
  assert.deepEqual(classifyPdfDownloadMetadata({ kind: "changed", id: 2 }), none);
});

test("source and Chromium/Firefox manifests have no website or page-data privileges", async () => {
  for (const path of ["manifest.json", "dist/manifest.json", "dist/firefox/manifest.json"]) {
    const manifest = JSON.parse(await readFile(join(root, path), "utf8"));
    assert.deepEqual(manifest.host_permissions, [], path);
    assert.deepEqual(manifest.permissions, [], path);
    for (const forbidden of [
      "content_scripts", "optional_host_permissions", "web_accessible_resources",
      "externally_connectable", "content_security_policy"
    ]) assert.equal(Object.hasOwn(manifest, forbidden), false, path + ": " + forbidden);
    assert.equal(JSON.stringify(manifest).includes("<all_urls>"), false, path);
    const optional = manifest.optional_permissions;
    assert.ok(optional === undefined ||
      JSON.stringify(optional) === JSON.stringify(["downloads"]));
  }
});

test("no browser page-collection APIs or network transports are introduced", async () => {
  const src = await readFile(new URL("../src/page-content-boundary.js", import.meta.url), "utf8");
  for (const forbidden of [
    "document.body", "innerHTML", "outerHTML", "querySelector(",
    "documentElement", "chrome.", "browser.", "executeScript(",
    "scripting.", "tabs.", "fetch(", "XMLHttpRequest",
    "sendNativeMessage(", "connectNative(", "localStorage", "storage.local",
    "node:fs", "node:child_process", "window.open("
  ]) assert.equal(src.includes(forbidden), false, forbidden);
});

test("the packaged background remains inert and cannot scrape pages", async () => {
  const source = await readFile(join(root, "src/background.js"), "utf8");
  for (const path of ["dist/background.js", "dist/firefox/background.js"]) {
    assert.equal(await readFile(join(root, path), "utf8"), source);
  }
  assert.equal(source,
    "// Inactive shared WebExtensions background entry point.\n" +
    "// Do not listen for messages, inspect PDFs or request native access here.\n" +
    "void 0;\n");
});
