import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";

import { detectPdfCandidate } from "../src/pdf-detection.js";
import { detectPdfNavigation } from "../src/pdf-navigation.js";
import { classifyPdfDocumentResource } from "../src/pdf-resource-scope.js";

const pdf = { isPdfCandidate: true, evidence: "url-path", authorizesOpen: false };
const none = { isPdfCandidate: false, evidence: "none", authorizesOpen: false };
const documentPdf = {
  isPdfCandidate: true, evidence: "document-url",
  authorizesScan: false, authorizesOpen: false
};
const noDocument = {
  isPdfCandidate: false, evidence: "none",
  authorizesScan: false, authorizesOpen: false
};
const navigation = (url, extras = {}) =>
  detectPdfNavigation({ url, tabId: 5, frameId: 0, ...extras });
const resource = (url, extras = {}) =>
  classifyPdfDocumentResource({
    url, tabId: 5, frameId: 0, type: "main_frame", ...extras
  });

// This creates an isolated, syntactically complete one-page PDF for test URLs.
// The identification helpers must never open, inspect, scan, or launch it.
function minimalPdf() {
  const objects = [
    "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
    "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
    "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
  ];
  const chunks = ["%PDF-1.4\n"];
  const offsets = [0];
  let position = Buffer.byteLength(chunks[0]);
  for (const object of objects) {
    offsets.push(position);
    chunks.push(object);
    position += Buffer.byteLength(object);
  }
  chunks.push("xref\n0 4\n0000000000 65535 f \n");
  for (const offset of offsets.slice(1)) {
    chunks.push(String(offset).padStart(10, "0") + " 00000 n \n");
  }
  chunks.push(
    "trailer\n<< /Size 4 /Root 1 0 R >>\n",
    "startxref\n" + position + "\n%%EOF\n"
  );
  return chunks.join("");
}

test("recognizes an existing local PDF through its escaped file URL", async (t) => {
  const folder = await mkdtemp(join(tmpdir(), "pdf-magic-local-url-"));
  t.after(() => rm(folder, { recursive: true, force: true }));
  const filename = join(folder, "Quarterly report ✓.PDF");
  await writeFile(filename, minimalPdf(), { flag: "wx" });
  assert.ok((await stat(filename)).size > 100);
  const url = pathToFileURL(filename).href;
  assert.ok(url.startsWith("file:///"));
  assert.match(url, /%20/);
  assert.match(url, /%E2%9C%93/i);

  assert.deepEqual(detectPdfCandidate({ url }), pdf);
  assert.deepEqual(navigation(url), pdf);
  assert.deepEqual(resource(url), documentPdf);

  // A URL-path hint does not prove the file is readable, present, or scanned.
  await rm(filename);
  assert.deepEqual(navigation(url), pdf);
  assert.deepEqual(resource(url), documentPdf);
});

test("accepts local file URL suffixes with case, escapes, query and fragment", () => {
  for (const url of [
    "file:///Users/example/My%20Documents/statement.pdf",
    "file:///Users/example/My%20Documents/statement.PDF#page=2",
    "file:///tmp/statement%2ePdF?view=1#page=3",
    "file:///tmp/%E2%9C%93%20report.pdf",
    "file://localhost/tmp/report.pdf",
    "FILE:///tmp/report.pdf"
  ]) {
    assert.deepEqual(detectPdfCandidate({ url }), pdf, url);
    assert.deepEqual(navigation(url), pdf, url);
    assert.deepEqual(resource(url), documentPdf, url);
  }
});

test("does not infer PDFs from local file URL query strings or misleading paths", () => {
  for (const url of [
    "file:///tmp/report.pdf.txt",
    "file:///tmp/report.pdf/preview",
    "file:///tmp/report",
    "file:///tmp/.pdf",
    "file:///tmp/report.txt?filename=report.pdf",
    "file:///tmp/report.txt#report.pdf",
    "file:///tmp/report%2F.pdf",
    "file:///tmp/report%5C.pdf",
    "file:///tmp/report%00.pdf",
    "file:///tmp/report%ZZ.pdf",
    "file:///tmp/report%252Epdf"
  ]) {
    assert.deepEqual(detectPdfCandidate({ url }), none, url);
    assert.deepEqual(navigation(url), none, url);
    assert.deepEqual(resource(url), noDocument, url);
  }
});

test("local file navigation must have a valid top-frame browser event", () => {
  const url = "file:///Users/example/letter.pdf";
  for (const extras of [
    { frameId: 1 }, { frameId: -1 }, { frameId: "0" },
    { tabId: -1 }, { tabId: "5" }, { tabId: 1.5 },
    { tabId: Number.MAX_SAFE_INTEGER + 1 }
  ]) {
    assert.deepEqual(navigation(url, extras), none);
    assert.deepEqual(resource(url, extras), noDocument);
  }
  for (const type of ["image", "script", "xmlhttprequest", "fetch", "other"]) {
    assert.deepEqual(resource(url, { type }), noDocument);
  }
});

test("non-PDF declared MIME never overrides file URL identification safety", () => {
  const url = "file:///Users/example/statement.pdf";
  assert.deepEqual(detectPdfCandidate({ url, mimeType: "text/html" }), none);
  assert.deepEqual(detectPdfCandidate({ url, mimeType: "image/png" }), none);
  assert.deepEqual(resource(url, { mimeType: "text/html" }), noDocument);
  assert.deepEqual(resource(url, { mimeType: "application/octet-stream" }), noDocument);

  // The navigation helper intentionally uses URL-path hints only; it does not
  // trust arbitrary MIME or filename fields from a navigation event.
  assert.deepEqual(navigation(url, {
    mimeType: "image/png", filename: "not-a-pdf.txt"
  }), pdf);
  assert.deepEqual(navigation("file:///tmp/view", {
    mimeType: "application/pdf", filename: "statement.pdf"
  }), none);
});

test("local URL classification is frozen, path-free and never permits opening", () => {
  const url = "file:///Users/private/Confidential%20report.pdf?token=secret";
  for (const result of [
    detectPdfCandidate({ url }), navigation(url), resource(url)
  ]) {
    assert.equal(Object.isFrozen(result), true);
    assert.equal(result.authorizesOpen, false);
    assert.equal(result.isPdfCandidate, true);
    assert.equal(JSON.stringify(result).includes("private"), false);
    assert.equal(JSON.stringify(result).includes("Confidential"), false);
    assert.equal(JSON.stringify(result).includes("secret"), false);
  }
  assert.equal(resource(url).authorizesScan, false);
});

test("file URL regression adds no file access, browser privileges, or scan bypass", async () => {
  const load = (path) => readFile(new URL(path, import.meta.url), "utf8");
  const [detector, navigator, scope, background, manifestText, pkg] =
    await Promise.all([
      load("../src/pdf-detection.js"),
      load("../src/pdf-navigation.js"),
      load("../src/pdf-resource-scope.js"),
      load("../src/background.js"),
      load("../manifest.json"),
      load("../package.json")
    ]);
  const manifest = JSON.parse(manifestText);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.match(JSON.parse(pkg).scripts.test, /tests\/\*\.test\.mjs/);
  for (const source of [detector, navigator, scope]) {
    for (const forbidden of [
      "node:fs", "fetch(", "XMLHttpRequest", "sendNativeMessage(",
      "connectNative(", "downloads.open(", "window.open(",
      "scan-and-open", "clamscan(", "addListener("
    ]) assert.equal(source.includes(forbidden), false, forbidden);
  }
});
