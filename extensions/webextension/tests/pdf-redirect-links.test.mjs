import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { detectPdfCandidate } from "../src/pdf-detection.js";
import { detectPdfNavigation } from "../src/pdf-navigation.js";
import { detectPdfResponseMime } from "../src/pdf-response-mime.js";
import { detectExtensionlessPdfResponse } from "../src/pdf-extensionless.js";

// These fixtures model independently authenticated *final* browser events.
// The extension does not follow redirects or subscribe to browser events.
const NONE = { isPdfCandidate: false, evidence: "none", authorizesOpen: false };
const PATH = { isPdfCandidate: true, evidence: "url-path", authorizesOpen: false };
const MIME = { isPdfCandidate: true, evidence: "mime-type", authorizesOpen: false };
const event = (url, extras = {}) => ({
  tabId: 9, frameId: 0, type: "main_frame", url, ...extras
});
const contentType = (mime) => [{ name: "Content-Type", value: mime }];

test("redirect status variants classify the committed PDF destination, not the source link", () => {
  for (const status of [301, 302, 303, 307, 308]) {
    const from = "https://example.test/go?file=private.pdf";
    const to = "https://files.example.test/documents/report.pdf?download=1#page=3";
    // A redirect notification, with a Location hint, is not a PDF navigation.
    assert.deepEqual(detectPdfNavigation(event(from, {
      statusCode: status, redirectUrl: to
    })), NONE, String(status));
    assert.deepEqual(detectPdfNavigation(event(to, {
      statusCode: 200, originalUrl: from
    })), PATH, String(status));
    assert.deepEqual(detectPdfCandidate({ url: to }), PATH, String(status));
  }
});

test("multihop redirects and encoded final PDF paths do not classify intermediate links", () => {
  const hops = [
    "https://example.test/start?next=statement.pdf",
    "https://example.test/session/redirect#statement.pdf",
    "https://cdn.example.test/reports/%72eport%2ePdF?token=opaque"
  ];
  for (const hop of hops.slice(0, -1)) {
    assert.deepEqual(detectPdfNavigation(event(hop, {
      redirectUrl: hops.at(-1), statusCode: 302
    })), NONE);
  }
  assert.deepEqual(detectPdfNavigation(event(hops.at(-1), {
    originalUrl: hops[0], statusCode: 200
  })), PATH);
});

test("a PDF-suffixed starting link redirected to HTML is not a final PDF", () => {
  const from = "https://example.test/report.pdf";
  const final = event("https://example.test/sign-in.html?next=report.pdf", {
    originalUrl: from, statusCode: 200,
    responseHeaders: contentType("text/html; charset=UTF-8")
  });
  // Only the committed destination is classified by future integration.
  assert.deepEqual(detectPdfNavigation(final), NONE);
  assert.deepEqual(detectPdfResponseMime(final), NONE);
  assert.deepEqual(detectExtensionlessPdfResponse(final), NONE);
});

test("a redirected extensionless PDF requires affirmative final response MIME", () => {
  const from = "https://example.test/statement.pdf?token=private";
  const destination = "https://example.test/download?id=123";
  const final = event(destination, {
    originalUrl: from, responseHeaders: contentType("application/pdf"),
    statusCode: 200
  });
  assert.deepEqual(detectPdfNavigation(final), NONE);
  assert.deepEqual(detectPdfResponseMime(final), MIME);
  assert.deepEqual(detectExtensionlessPdfResponse(final), MIME);
  for (const responseHeaders of [
    [], contentType("text/html"), contentType("application/octet-stream"),
    [ ...contentType("application/pdf"), ...contentType("text/html") ]
  ]) {
    assert.deepEqual(detectExtensionlessPdfResponse(event(destination, {
      originalUrl: from, responseHeaders
    })), NONE);
  }
});

test("redirect Location and original-link hints never substitute for a final PDF URL or MIME", () => {
  const target = "https://example.test/report.pdf";
  const final = event("https://example.test/landing?document=report.pdf", {
    redirectUrl: target, originalUrl: target, filename: "report.pdf",
    responseHeaders: [{ name: "Location", value: target }],
    statusCode: 302
  });
  assert.deepEqual(detectPdfNavigation(final), NONE);
  assert.deepEqual(detectPdfResponseMime(final), NONE);
  assert.deepEqual(detectExtensionlessPdfResponse(final), NONE);
  // The original URL does not override a known non-PDF final declaration.
  assert.deepEqual(detectPdfCandidate({
    url: final.url, mimeType: "text/html", filename: "report.pdf"
  }), NONE);
});

test("untrusted, malformed and non-web redirect destinations cannot become navigation candidates", () => {
  for (const url of [
    "https://example.test/report%ZZ.pdf",
    "https://example.test/report%2F.pdf",
    "https://example.test/report%00.pdf",
    "blob:https://example.test/report.pdf",
    "data:application/pdf,content",
    "javascript:alert('report.pdf')",
    "ftp://example.test/report.pdf"
  ]) {
    assert.deepEqual(detectPdfNavigation(event(url, {
      originalUrl: "https://example.test/go", statusCode: 200
    })), NONE, url);
    assert.deepEqual(detectExtensionlessPdfResponse(event(url, {
      originalUrl: "https://example.test/go",
      responseHeaders: contentType("application/pdf")
    })), NONE, url);
  }
  // A misleading executable suffix alone is not a PDF path, but a trusted
  // final PDF MIME declaration can still identify extensionless PDF bytes.
  const disguised = event("https://example.test/report.pdf.exe", {
    responseHeaders: contentType("application/pdf")
  });
  assert.deepEqual(detectPdfNavigation(disguised), NONE);
  assert.deepEqual(detectExtensionlessPdfResponse(disguised), MIME);
  for (const patch of [
    { frameId: 2 }, { frameId: -1 }, { tabId: -1 }, { tabId: "9" }
  ]) {
    const final = event("https://example.test/report.pdf", patch);
    assert.deepEqual(detectPdfNavigation(final), NONE);
    assert.deepEqual(detectPdfResponseMime({
      ...final, responseHeaders: contentType("application/pdf")
    }), NONE);
  }
});

test("redirect test evidence is immutable, path-free and never an opening grant", () => {
  const samples = [
    detectPdfNavigation(event("https://private.test/report.pdf?token=secret")),
    detectPdfNavigation(event("https://private.test/landing?token=secret")),
    detectExtensionlessPdfResponse(event("https://private.test/download?token=secret", {
      responseHeaders: contentType("application/pdf")
    })),
    detectPdfResponseMime(event("https://private.test/page", {
      responseHeaders: contentType("text/html")
    }))
  ];
  for (const result of samples) {
    assert.equal(Object.isFrozen(result), true);
    assert.deepEqual(Object.keys(result).sort(),
      ["authorizesOpen", "evidence", "isPdfCandidate"]);
    assert.equal(result.authorizesOpen, false);
    assert.equal(JSON.stringify(result).includes("private"), false);
    assert.equal(JSON.stringify(result).includes("secret"), false);
  }
});

test("redirect regression is included in CI without activating interception or altering preferences", async () => {
  const read = path => readFile(new URL(path, import.meta.url), "utf8");
  const [ci, manifestText, background, navigation, extensionless] = await Promise.all([
    read("../../../.github/workflows/ci.yml"),
    read("../manifest.json"),
    read("../src/background.js"),
    read("../src/pdf-navigation.js"),
    read("../src/pdf-extensionless.js")
  ]);
  assert.match(ci, /node --test tests\/pdf-redirect-links\.test\.mjs/);
  const manifest = JSON.parse(manifestText);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  for (const source of [navigation, extensionless]) {
    for (const forbidden of [
      "addListener(", "permissions.request", "fetch(", "XMLHttpRequest",
      "sendNativeMessage(", "connectNative(", "downloads.open(", "scan-and-open"
    ]) assert.equal(source.includes(forbidden), false, forbidden);
  }
});
