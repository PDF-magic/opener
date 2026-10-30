import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  EXPLICIT_PDF_SCAN_REQUEST_VERSION, EXPLICIT_PDF_SCAN_REQUEST_FIELDS,
  EXPLICIT_PDF_SCAN_REQUEST_SOURCES, describeExplicitPdfScanRequest
} from "../src/explicit-pdf-scan-request.js";

const request = (source = "toolbar", more = {}) => ({
  version: 1, requestId: "scan_attempt_42", source,
  tabId: 8, frameId: 0, selectionId: "selected_document_42",
  userInitiated: true, ...more
});
const describe = describeExplicitPdfScanRequest;

test("defines the exact, versioned information needed to describe a scan request", () => {
  assert.equal(EXPLICIT_PDF_SCAN_REQUEST_VERSION, 1);
  assert.deepEqual(EXPLICIT_PDF_SCAN_REQUEST_FIELDS, [
    "version", "requestId", "source", "tabId", "frameId",
    "selectionId", "userInitiated"
  ]);
  assert.deepEqual(EXPLICIT_PDF_SCAN_REQUEST_SOURCES, [
    "toolbar", "pdf-link", "embedded-pdf"
  ]);
  assert.ok(Object.isFrozen(EXPLICIT_PDF_SCAN_REQUEST_FIELDS));
  assert.ok(Object.isFrozen(EXPLICIT_PDF_SCAN_REQUEST_SOURCES));
  const result = describe(request());
  assert.deepEqual(result, {
    version: 1, requestId: "scan_attempt_42", source: "toolbar",
    tabId: 8, frameId: 0, selectionId: "selected_document_42",
    userInitiated: true, status: "metadata-only",
    requiresTrustedSelection: true, requiresNativeFileValidation: true,
    scanVerified: false, authorizesScan: false, authorizesOpen: false
  });
  assert.equal(Object.isFrozen(result), true);
});

test("supports toolbar, link and embedded PDF request locations without opening", () => {
  const scenarios = [
    request(),
    request("pdf-link", { frameId: 0 }),
    request("pdf-link", { frameId: 7 }),
    request("embedded-pdf", { frameId: 7 }),
    request("embedded-pdf", { frameId: 0 })
  ];
  for (const item of scenarios) {
    const result = describe(item);
    assert.equal(result.source, item.source);
    assert.equal(result.tabId, item.tabId);
    assert.equal(result.frameId, item.frameId);
    assert.equal(result.authorizesScan, false);
    assert.equal(result.authorizesOpen, false);
    assert.equal(result.scanVerified, false);
  }
  assert.equal(describe(request("toolbar", { frameId: 1 })), null);
});

test("requires an explicit request, valid request ID and separate selection identity", () => {
  for (const value of [false, undefined, null, 1, "true"]) {
    assert.equal(describe(request("toolbar", { userInitiated: value })), null);
  }
  for (const item of [
    { version: 2 }, { version: "1" }, { source: "download" },
    { source: "manual" }, { source: "external-page" },
    { requestId: "" }, { requestId: "a".repeat(81) },
    { requestId: "an id" }, { requestId: "../file.pdf" },
    { requestId: "https://example.test/file.pdf" },
    { selectionId: "" }, { selectionId: "b".repeat(81) },
    { selectionId: "/private/document.pdf" },
    { selectionId: "selection.token" },
    { selectionId: "scan_attempt_42" }
  ]) assert.equal(describe(request("toolbar", item)), null, JSON.stringify(item));
});

test("requires valid tab and frame identity rather than page-provided names", () => {
  for (const invalid of [
    { tabId: -1 }, { tabId: "8" }, { tabId: 1.25 },
    { tabId: Number.MAX_SAFE_INTEGER + 1 }, { tabId: null },
    { frameId: -1 }, { frameId: "0" }, { frameId: 0.2 },
    { frameId: Number.MAX_SAFE_INTEGER + 1 }, { frameId: null },
    { source: "toolbar", frameId: 5 }
  ]) assert.equal(describe(request("toolbar", invalid)), null, JSON.stringify(invalid));
  assert.ok(describe(request("embedded-pdf", {
    tabId: Number.MAX_SAFE_INTEGER, frameId: Number.MAX_SAFE_INTEGER
  })));
});

test("rejects URLs, file paths, content, arbitrary verdicts and extra fields", () => {
  for (const unexpected of [
    { url: "https://example.test/a.pdf?token=secret" },
    { localPath: "/private/paper.pdf" },
    { filename: "paper.pdf" }, { pdfBytes: "%PDF-1.7" },
    { mimeType: "application/pdf" }, { clean: true },
    { scanVerified: true }, { authorizesOpen: true },
    { nativePermission: true }, { isPdfCandidate: true },
    { allowScan: true }, { destination: "/Applications/Preview.app" },
    { timestamp: Date.now() }, { browserTab: { url: "private" } }
  ]) assert.equal(describe(request("toolbar", unexpected)), null);
  assert.equal(describe(request("toolbar", { selectionId: "blob:https://example.test/id" })), null);
});

test("malformed records, symbols, accessors and hostile objects fail closed", () => {
  let reads = 0;
  const getter = request();
  Object.defineProperty(getter, "selectionId", { get() {
    reads++;
    return "selected_document_42";
  } });
  const inherited = Object.create(request());
  const symbol = request();
  symbol[Symbol("secret")] = "private";
  const proxy = new Proxy(request(), { ownKeys() { throw Error("private"); } });
  for (const bad of [
    undefined, null, 42, [], "scan", new Date(), getter,
    inherited, symbol, proxy, request("toolbar", { version: undefined }),
    request("toolbar", { requestId: Symbol("secret") })
  ]) assert.equal(describe(bad), null);
  assert.equal(reads, 0);
  const nullPrototype = Object.assign(Object.create(null), request());
  assert.equal(describe(nullPrototype).status, "metadata-only");
});

test("returned metadata is detached and cannot be promoted into authorization", () => {
  const original = request("embedded-pdf", { frameId: 5 });
  const result = describe(original);
  original.tabId = -1;
  original.requestId = "changed";
  original.selectionId = "/private/other.pdf";
  assert.equal(result.tabId, 8);
  assert.equal(result.requestId, "scan_attempt_42");
  assert.equal(result.selectionId, "selected_document_42");
  assert.equal(result.authorizesScan, false);
  assert.equal(result.authorizesOpen, false);
  assert.equal(result.status, "metadata-only");
  assert.equal(JSON.stringify(result).includes("/private"), false);
  assert.equal(Object.isFrozen(result), true);
});

test("schema has no browser listener, native transport, filesystem or scanner bypass", async () => {
  const load = path => readFile(new URL(path, import.meta.url), "utf8");
  const [source, manifestText, background, packageText, ci] = await Promise.all([
    load("../src/explicit-pdf-scan-request.js"),
    load("../manifest.json"),
    load("../src/background.js"),
    load("../package.json"),
    load("../../../.github/workflows/ci.yml")
  ]);
  for (const token of [
    "chrome.", "browser.", "addListener(", "contextMenus.create",
    "sendNativeMessage(", "connectNative(", "fetch(", "XMLHttpRequest",
    "WebSocket", "window.open(", "downloads.open(", "node:fs",
    "scan-and-open", "clamscan(", "querySelector(", "localStorage"
  ]) assert.equal(source.includes(token), false, token);
  const manifest = JSON.parse(manifestText);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.match(JSON.parse(packageText).scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(ci, /npm test/);
});
